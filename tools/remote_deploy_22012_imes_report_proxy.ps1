$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# REQ-IMES-REPORT-22012-PROXY-20260808
$listenAddress = '10.30.220.12'
$reportPort = 18084
$targetHost = '10.10.181.205'
$targetPort = 8080
$nginxRoot = 'C:\Users\Administrator\Desktop\nginx-1.29.3'
$nginxExe = Join-Path $nginxRoot 'nginx.exe'
$nginxConfig = Join-Path $nginxRoot 'conf\nginx.conf'
$patcher = 'C:\Users\Administrator\AppData\Local\Temp\patch_22012_nginx_imes_report.py'
$python = 'C:\Program Files\Python311\python.exe'
$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$backupRoot = Join-Path $projectRoot 'logs\deploy_backups'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $backupRoot ('22012_imes_report_proxy_' + $stamp)
$firewallName = 'BFIMESReport18084VpnClient'
$protectedPorts = @(8093, 8768, 8094, 8770)
$configPatched = $false
$firewallAdded = $false

function Get-PortPidMap {
    param([int[]]$Ports)
    $result = [ordered]@{}
    foreach ($port in $Ports) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
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

function Invoke-Nginx {
    param([string[]]$Arguments)
    Push-Location -LiteralPath $nginxRoot
    try {
        & $nginxExe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "nginx $($Arguments -join ' ') 失败，exit=$LASTEXITCODE" }
    } finally { Pop-Location }
}

function Get-VpnClientAddress {
    $raw = if ($env:SSH_CONNECTION) { $env:SSH_CONNECTION } else { $env:SSH_CLIENT }
    if (-not $raw) { throw 'SSH_CONNECTION/SSH_CLIENT 不存在，无法限定报表转发防火墙来源' }
    $address = ($raw -split '\s+')[0]
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($address, [ref]$parsed)) { throw "无法解析 VPN 客户端地址：$address" }
    return $address
}

function Ensure-Firewall {
    param([string]$RemoteAddress)
    $existing = Get-NetFirewallRule -Name $firewallName -ErrorAction SilentlyContinue
    if ($existing) {
        $filters = @(Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $existing -ErrorAction Stop)
        $remoteValues = @($filters | ForEach-Object { $_.RemoteAddress })
        if (($remoteValues -notcontains $RemoteAddress) -and ($remoteValues -notcontains 'Any')) {
            throw "防火墙规则 $firewallName 已存在但未允许当前 VPN 客户端 $RemoteAddress"
        }
        return $false
    }
    New-NetFirewallRule -Name $firewallName -DisplayName 'BF IMES report relay 18084 (VPN client only)' `
        -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP `
        -LocalAddress $listenAddress -LocalPort $reportPort -RemoteAddress $RemoteAddress | Out-Null
    $script:firewallAdded = $true
    return $true
}

function Invoke-HttpCheck {
    param([string]$Uri, [string]$Name)
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 60
    if ([int]$response.StatusCode -ne 200) { throw "$Name HTTP 状态异常：$($response.StatusCode)" }
    return $response
}

function Assert-NginxListener {
    param([int]$Port)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
    if ($process.ProcessName -ne 'nginx' -or $process.Path -ne $nginxExe) {
        throw "$Port 不是预期 Nginx：PID=$($listener.OwningProcess) Path=$($process.Path)"
    }
    return [ordered]@{ port = $Port; pid = [int]$listener.OwningProcess; path = $process.Path }
}

if (-not (Test-Path -LiteralPath $nginxExe)) { throw "找不到 Nginx：$nginxExe" }
if (-not (Test-Path -LiteralPath $nginxConfig)) { throw "找不到 Nginx 配置：$nginxConfig" }
if (-not (Test-Path -LiteralPath $patcher)) { throw "找不到报表 Nginx 补丁器：$patcher" }
if (-not (Test-Path -LiteralPath $python)) { throw "找不到 Python：$python" }

$clientAddress = Get-VpnClientAddress
if (-not (Test-NetConnection $targetHost -Port $targetPort -InformationLevel Quiet)) {
    throw "报表源站不可达：$targetHost`:$targetPort"
}
$existingReportListener = Get-NetTCPConnection -State Listen -LocalPort $reportPort -ErrorAction SilentlyContinue
$configText = Get-Content -LiteralPath $nginxConfig -Raw -Encoding UTF8
if ($existingReportListener -and ($configText -notmatch 'OPS-22012-IMES-REPORT-PROXY-20260808')) {
    throw "18084 已被其他进程监听，拒绝覆盖"
}

$nginxListener = Get-NetTCPConnection -State Listen -LocalPort 18080 -ErrorAction Stop | Select-Object -First 1
$nginxProcess = Get-Process -Id $nginxListener.OwningProcess -ErrorAction Stop
if ($nginxProcess.ProcessName -ne 'nginx' -or $nginxProcess.Path -ne $nginxExe) {
    throw "18080 不是预期 Nginx：PID=$($nginxListener.OwningProcess) Path=$($nginxProcess.Path)"
}

$protectedBefore = Get-PortPidMap -Ports $protectedPorts
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Copy-Item -LiteralPath $nginxConfig -Destination (Join-Path $backupDir 'nginx.conf.before') -Force
(& netsh.exe advfirewall firewall show rule name=$firewallName 2>&1 | Out-String) |
    Set-Content -LiteralPath (Join-Path $backupDir 'firewall.before.txt') -Encoding UTF8
($protectedBefore | ConvertTo-Json) | Set-Content -LiteralPath (Join-Path $backupDir 'protected_pids.before.json') -Encoding UTF8

try {
    $patchResultText = & $python -X utf8 $patcher --config $nginxConfig
    if ($LASTEXITCODE -ne 0) { throw "报表 Nginx 补丁器失败，exit=$LASTEXITCODE" }
    $patchResult = $patchResultText | ConvertFrom-Json
    $configPatched = [bool]$patchResult.changed

    Invoke-Nginx -Arguments @('-t')
    Invoke-Nginx -Arguments @('-s', 'reload')
    [void](Ensure-Firewall -RemoteAddress $clientAddress)
    $imesListener = Assert-NginxListener -Port 18080
    $reportNginxListener = Assert-NginxListener -Port $reportPort
    $imes = Invoke-HttpCheck -Uri 'http://127.0.0.1:18080/imes.web/' -Name 'IMES 主站'

    $reportUri = 'http://127.0.0.1:18084/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht'
    $report = Invoke-HttpCheck -Uri $reportUri -Name '报表初始页'
    if ($report.Content -notmatch 'Raqsoft Fill Report') { throw '报表初始页缺少 Raqsoft 标记' }
    if ($report.Content -notmatch '10\.30\.220\.12:18084') { throw '报表绝对地址重写未生效' }
    if ($report.Content -match '10\.10\.181\.205:8080') { throw '报表 HTML 仍暴露源站绝对地址' }

    $jquery = Invoke-HttpCheck -Uri 'http://127.0.0.1:18084/demo/raqsoft/easyui/jquery.min.js' -Name '报表脚本资源'
    if ($jquery.Content.Length -lt 1000) { throw '报表脚本资源内容过短' }

    $protectedAfter = Get-PortPidMap -Ports $protectedPorts
    Assert-ProtectedPidsUnchanged -Before $protectedBefore -After $protectedAfter
    $result = [ordered]@{
        ok = $true
        requirement = 'REQ-IMES-REPORT-22012-PROXY-20260808'
        deployed_at = (Get-Date).ToString('s')
        backup_dir = $backupDir
        vpn_client_address = $clientAddress
        listen = "$listenAddress`:$reportPort"
        upstream = "$targetHost`:$targetPort"
        report_initial = [ordered]@{ status = [int]$report.StatusCode; content_length = $report.Content.Length; uri = $reportUri }
        asset_probe = [ordered]@{ status = [int]$jquery.StatusCode; content_length = $jquery.Content.Length }
        imes_main = [ordered]@{ status = [int]$imes.StatusCode; content_length = $imes.Content.Length; listener = $imesListener }
        report_listener = $reportNginxListener
        nginx_sha256 = (Get-FileHash -LiteralPath $nginxConfig -Algorithm SHA256).Hash
        config_changed = $configPatched
        protected_before = $protectedBefore
        protected_after = $protectedAfter
    }
    ($result | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath (Join-Path $backupDir 'deployment_result.json') -Encoding UTF8
    $result | ConvertTo-Json -Depth 8
} catch {
    $deployError = $_
    if ($firewallAdded) { Remove-NetFirewallRule -Name $firewallName -ErrorAction SilentlyContinue }
    if ($configPatched -and (Test-Path -LiteralPath (Join-Path $backupDir 'nginx.conf.before'))) {
        Copy-Item -LiteralPath (Join-Path $backupDir 'nginx.conf.before') -Destination $nginxConfig -Force
        try { Invoke-Nginx -Arguments @('-t'); Invoke-Nginx -Arguments @('-s', 'reload') } catch { Write-Error "回滚 Nginx 失败：$($_.Exception.Message)" }
    }
    throw $deployError
}
