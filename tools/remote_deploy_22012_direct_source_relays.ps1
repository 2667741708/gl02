$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-22012-DIRECT-SOURCE-RELAYS-20260805
$listenAddress = "10.30.220.12"
$nginxRoot = "C:\Users\Administrator\Desktop\nginx-1.29.3"
$nginxExe = Join-Path $nginxRoot "nginx.exe"
$nginxConfig = Join-Path $nginxRoot "conf\nginx.conf"
$patcher = "C:\Users\Administrator\AppData\Local\Temp\patch_22012_nginx_imes_web.py"
$python = "C:\Program Files\Python311\python.exe"
$projectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$backupRoot = Join-Path $projectRoot "logs\deploy_backups"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $backupRoot ("22012_direct_source_relays_" + $stamp)
$protectedPorts = @(8093, 8768, 8094, 8770)
$addedPortProxy = New-Object System.Collections.Generic.List[int]
$addedFirewall = New-Object System.Collections.Generic.List[string]
$nginxPatched = $false

function Get-PortPidMap {
    param([int[]]$Ports)
    $result = [ordered]@{}
    foreach ($port in $Ports) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -First 1
        $result[[string]$port] = if ($listener) { [int]$listener.OwningProcess } else { $null }
    }
    return $result
}

function Assert-ProtectedPidsUnchanged {
    param($Before, $After)
    foreach ($port in $protectedPorts) {
        $key = [string]$port
        if ($Before[$key] -ne $After[$key]) {
            throw "受保护端口 $port 的 PID 发生变化：$($Before[$key]) -> $($After[$key])"
        }
    }
}

function Assert-TargetReachable {
    param([string]$Name, [string]$HostName, [int]$Port)
    if (-not (Test-NetConnection $HostName -Port $Port -InformationLevel Quiet)) {
        throw "目标不可达：$Name $HostName`:$Port"
    }
}

function Ensure-PortProxy {
    param([int]$ListenPort, [string]$ConnectAddress, [int]$ConnectPort)
    $rows = (& netsh.exe interface portproxy show v4tov4 2>&1 | Out-String)
    $exact = "(?m)^\s*" + [regex]::Escape($listenAddress) + "\s+" + $ListenPort +
        "\s+" + [regex]::Escape($ConnectAddress) + "\s+" + $ConnectPort + "\s*$"
    if ($rows -match $exact) {
        return $false
    }
    $conflict = "(?m)^\s*\S+\s+" + $ListenPort + "\s+\S+\s+\d+\s*$"
    if ($rows -match $conflict) {
        throw "端口代理 $ListenPort 已存在其他映射，拒绝覆盖"
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $ListenPort -ErrorAction SilentlyContinue
    if ($listener) {
        throw "端口 $ListenPort 已由 PID $($listener[0].OwningProcess) 监听，拒绝覆盖"
    }
    & netsh.exe interface portproxy add v4tov4 `
        listenaddress=$listenAddress listenport=$ListenPort `
        connectaddress=$ConnectAddress connectport=$ConnectPort protocol=tcp | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "新增端口代理 $ListenPort 失败，netsh exit=$LASTEXITCODE"
    }
    $addedPortProxy.Add($ListenPort)
    return $true
}

function Ensure-FirewallRule {
    param([string]$Name, [int]$Port, [string]$RemoteAddress)
    $existing = Get-NetFirewallRule -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        return $false
    }
    New-NetFirewallRule -Name $Name -DisplayName ("BF Source Relay " + $Port + " (VPN client only)") `
        -Direction Inbound -Action Allow -Enabled True `
        -Profile Any -Protocol TCP -LocalAddress $listenAddress -LocalPort $Port `
        -RemoteAddress $RemoteAddress | Out-Null
    $addedFirewall.Add($Name)
    return $true
}

function Invoke-Nginx {
    param([string[]]$Arguments)
    Push-Location -LiteralPath $nginxRoot
    try {
        & $nginxExe @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "nginx $($Arguments -join ' ') 失败，exit=$LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

function Test-ImesProxy {
    $lastError = $null
    foreach ($attempt in 1..12) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:18080/imes.web/" -TimeoutSec 15
            if ([int]$response.StatusCode -eq 200 -and $response.RawContentLength -gt 0) {
                return [ordered]@{
                    ok = $true
                    status = [int]$response.StatusCode
                    final_uri = [string]$response.BaseResponse.ResponseUri
                    content_type = [string]$response.Headers["Content-Type"]
                    content_length = [int]$response.RawContentLength
                    has_imes_marker = [bool]($response.Content -match "imes|iMES|冀南")
                }
            }
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    }
    throw "IMES Web 代理未通过 HTTP 验收：$lastError"
}

if (-not (Test-Path -LiteralPath $nginxExe)) { throw "找不到 Nginx：$nginxExe" }
if (-not (Test-Path -LiteralPath $nginxConfig)) { throw "找不到 Nginx 配置：$nginxConfig" }
if (-not (Test-Path -LiteralPath $patcher)) { throw "找不到配置补丁器：$patcher" }
if (-not (Test-Path -LiteralPath $python)) { throw "找不到 Python：$python" }

$sshConnection = [string]$env:SSH_CONNECTION
if (-not $sshConnection) { throw "SSH_CONNECTION 不存在，无法把防火墙限定到当前 VPN 客户端" }
$clientAddress = ($sshConnection -split "\s+")[0]
$parsedClientAddress = $null
if (-not [Net.IPAddress]::TryParse($clientAddress, [ref]$parsedClientAddress)) {
    throw "无法解析当前 VPN 客户端地址：$clientAddress"
}

$nginxListener = Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction Stop | Select-Object -First 1
$nginxProcess = Get-Process -Id $nginxListener.OwningProcess -ErrorAction Stop
if ($nginxProcess.ProcessName -ne "nginx" -or $nginxProcess.Path -ne $nginxExe) {
    throw "18080 不是预期 Nginx：PID=$($nginxListener.OwningProcess) Path=$($nginxProcess.Path)"
}

Assert-TargetReachable -Name "IMES Web" -HostName "10.10.181.209" -Port 8080
Assert-TargetReachable -Name "IMES Vastbase" -HostName "10.10.181.195" -Port 5432
Assert-TargetReachable -Name "pSpace" -HostName "10.22.181.243" -Port 8889

$protectedBefore = Get-PortPidMap -Ports $protectedPorts
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -LiteralPath $nginxConfig -Destination (Join-Path $backupDir "nginx.conf.before") -Force
(& netsh.exe interface portproxy dump 2>&1 | Out-String) |
    Set-Content -LiteralPath (Join-Path $backupDir "portproxy.before.txt") -Encoding UTF8
($protectedBefore | ConvertTo-Json) |
    Set-Content -LiteralPath (Join-Path $backupDir "protected_pids.before.json") -Encoding UTF8

try {
    $patchResultText = & $python -X utf8 $patcher --config $nginxConfig
    if ($LASTEXITCODE -ne 0) { throw "Nginx配置补丁器失败，exit=$LASTEXITCODE" }
    $patchResult = $patchResultText | ConvertFrom-Json
    $nginxPatched = [bool]$patchResult.changed

    Invoke-Nginx -Arguments @("-t")
    Invoke-Nginx -Arguments @("-s", "reload")
    $http = Test-ImesProxy

    [void](Ensure-PortProxy -ListenPort 15433 -ConnectAddress "10.10.181.195" -ConnectPort 5432)
    [void](Ensure-PortProxy -ListenPort 18889 -ConnectAddress "10.22.181.243" -ConnectPort 8889)
    [void](Ensure-FirewallRule -Name "BFSourceRelay18080VpnClient" -Port 18080 -RemoteAddress $clientAddress)
    [void](Ensure-FirewallRule -Name "BFSourceRelay15433VpnClient" -Port 15433 -RemoteAddress $clientAddress)
    [void](Ensure-FirewallRule -Name "BFSourceRelay18889VpnClient" -Port 18889 -RemoteAddress $clientAddress)

    foreach ($port in 15433, 18889) {
        if (-not (Test-NetConnection $listenAddress -Port $port -InformationLevel Quiet)) {
            throw "220.12 本机转发端口 $port 未通过 TCP 验收"
        }
    }

    $protectedAfter = Get-PortPidMap -Ports $protectedPorts
    Assert-ProtectedPidsUnchanged -Before $protectedBefore -After $protectedAfter

    $result = [ordered]@{
        ok = $true
        requirement = "OPS-22012-DIRECT-SOURCE-RELAYS-20260805"
        deployed_at = (Get-Date).ToString("s")
        backup_dir = $backupDir
        vpn_client_address = $clientAddress
        nginx_config = $nginxConfig
        nginx_sha256 = (Get-FileHash -LiteralPath $nginxConfig -Algorithm SHA256).Hash
        nginx_patched = $nginxPatched
        imes_web = $http
        relays = @(
            [ordered]@{ listen = "$listenAddress`:18080"; target = "10.10.181.209:8080"; protocol = "HTTP via Nginx" },
            [ordered]@{ listen = "$listenAddress`:15433"; target = "10.10.181.195:5432"; protocol = "TCP portproxy" },
            [ordered]@{ listen = "$listenAddress`:18889"; target = "10.22.181.243:8889"; protocol = "TCP portproxy" }
        )
        protected_before = $protectedBefore
        protected_after = $protectedAfter
        portproxy = (& netsh.exe interface portproxy show v4tov4 2>&1 | Out-String).Trim()
    }
    ($result | ConvertTo-Json -Depth 8) |
        Set-Content -LiteralPath (Join-Path $backupDir "deployment_result.json") -Encoding UTF8
    $result | ConvertTo-Json -Depth 8
} catch {
    $deployError = $_
    foreach ($name in $addedFirewall) {
        Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
    }
    foreach ($port in $addedPortProxy) {
        & netsh.exe interface portproxy delete v4tov4 listenaddress=$listenAddress listenport=$port protocol=tcp | Out-Null
    }
    if ($nginxPatched -and (Test-Path -LiteralPath (Join-Path $backupDir "nginx.conf.before"))) {
        Copy-Item -LiteralPath (Join-Path $backupDir "nginx.conf.before") -Destination $nginxConfig -Force
        try {
            Invoke-Nginx -Arguments @("-t")
            Invoke-Nginx -Arguments @("-s", "reload")
        } catch {
            Write-Error "回滚Nginx时发生错误：$($_.Exception.Message)"
        }
    }
    throw $deployError
}
