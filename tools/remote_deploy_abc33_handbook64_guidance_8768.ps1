$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_handbook64_guidance'
$service = 'BFV4PreviewWs8768'
$python = 'C:\Program Files\Python311\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\abc33_handbook64_guidance_8768_$stamp"
$files = @(
    [ordered]@{
        staged = 'abc_rule_guidance.py'
        relative = '自动诊断服务\abc_rule_guidance.py'
        sha256 = '3A2BB9DD8FFFC102EC666C270773123EC569470810941BA83F86DBA0112F0A99'
    },
    [ordered]@{
        staged = 'abc_rule_catalog.py'
        relative = '自动诊断服务\abc_rule_catalog.py'
        sha256 = '6A3ECD620C4AFD703EAD1913930251E92BE66F2B3EE2F6F3F3A252E1143359A6'
    },
    [ordered]@{
        staged = 'abc_runtime_store.py'
        relative = '自动诊断服务\abc_runtime_store.py'
        sha256 = '454A81253333B51D30E4D51657A5D47264DBA0F82A21608355BF40B8926D8094'
    }
)

function Get-PortPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Expected, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (($null -ne (Get-PortPid $Port)) -eq $Expected) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "port $Port did not reach listening=$Expected"
}

$before = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $before["p$port"] = Get-PortPid $port
    if (-not $before["p$port"]) { throw "missing protected listener: $port" }
}

foreach ($entry in $files) {
    $stagedPath = Join-Path $stage $entry.staged
    if (-not (Test-Path -LiteralPath $stagedPath)) { throw "missing staged file: $stagedPath" }
    $actualHash = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash
    if ($actualHash -ne $entry.sha256) { throw "staged hash mismatch: $($entry.staged)" }
    & $python -m py_compile $stagedPath
    if ($LASTEXITCODE -ne 0) { throw "syntax validation failed: $($entry.staged)" }
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($entry in $files) {
    $target = Join-Path $root $entry.relative
    $entry.existed = Test-Path -LiteralPath $target
    if ($entry.existed) {
        Copy-Item -LiteralPath $target -Destination (Join-Path $backup $entry.staged) -Force
    }
}

$deploymentStarted = $false
$deploymentSucceeded = $false
try {
    Stop-Service -Name $service -Force
    Wait-Port 8768 $false 90
    $deploymentStarted = $true
    foreach ($entry in $files) {
        $target = Join-Path $root $entry.relative
        Copy-Item -LiteralPath (Join-Path $stage $entry.staged) -Destination "$target.next" -Force
        Move-Item -LiteralPath "$target.next" -Destination $target -Force
    }
    Start-Service -Name $service
    Wait-Port 8768 $true 150
    $deploymentSucceeded = $true
} catch {
    if ($deploymentStarted) {
        Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
        Wait-Port 8768 $false 90
        foreach ($entry in $files) {
            $target = Join-Path $root $entry.relative
            $backupFile = Join-Path $backup $entry.staged
            if ($entry.existed) {
                Copy-Item -LiteralPath $backupFile -Destination $target -Force
            } elseif (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
            }
        }
    }
    throw
} finally {
    if ((Get-Service -Name $service).Status -ne 'Running') {
        Start-Service -Name $service -ErrorAction SilentlyContinue
    }
    Wait-Port 8768 $true 150
}

$after = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $after["p$port"] = Get-PortPid $port
}
foreach ($port in 8093, 8094, 8770, 11434) {
    if ($after["p$port"] -ne $before["p$port"]) { throw "protected PID changed: $port" }
}
if (-not $deploymentSucceeded) { throw '8768 deployment did not complete' }

$hashes = foreach ($entry in $files) {
    $target = Join-Path $root $entry.relative
    $actualHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actualHash -ne $entry.sha256) { throw "deployed hash mismatch: $($entry.relative)" }
    [ordered]@{ path = $entry.relative; sha256 = $actualHash }
}

[ordered]@{
    ok = $true
    backup = $backup
    service = (Get-Service -Name $service).Status.ToString()
    before = $before
    after = $after
    hashes = $hashes
}|ConvertTo-Json -Depth 7
