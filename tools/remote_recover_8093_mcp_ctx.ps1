$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$wsServiceName = 'BFV4PreviewWs8768'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$source = 'C:\Users\Administrator\AppData\Local\Temp\mcp_conversation_context.py'
$target = Join-Path $root '高炉前端数据\智能助手\backend\mcp_conversation_context.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\8093_mcp_ctx_recovery_$stamp"
$backup = Join-Path $backupRoot 'mcp_conversation_context.py'
$installed = $false

if (-not (Test-Path -LiteralPath $source)) { throw "missing recovery payload: $source" }
if (-not (Test-Path -LiteralPath $target)) { throw "missing recovery target: $target" }
if (-not (Test-Path -LiteralPath $manager)) { throw "missing service manager: $manager" }
if (-not (Test-Path -LiteralPath $configPath)) { throw "missing service config: $configPath" }

$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$listen8768Before = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
if ($wsBefore.Status -ne 'Running') { throw '8768 must be running before recovery' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item -LiteralPath $target -Destination $backup -Force

try {
    $service = Get-Service -Name $serviceName -ErrorAction Stop
    if ($service.Status -ne 'Stopped') {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath
        if ($LASTEXITCODE -ne 0) { throw 'failed to stop paused 8093 service' }
    }

    $temporary = "$target.codex-$stamp.tmp"
    Copy-Item -LiteralPath $source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $target -Force
    $installed = $true

    & 'C:\Program Files\Python311\python.exe' -m py_compile $target
    if ($LASTEXITCODE -ne 0) { throw 'mcp context syntax validation failed' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath
    if ($LASTEXITCODE -ne 0) { throw 'failed to start 8093 after dependency recovery' }

    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        $service = Get-Service -Name $serviceName -ErrorAction Stop
        $listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue
        if ($service.Status -eq 'Running' -and $listener) { break }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($service.Status -ne 'Running' -or -not $listener) { throw '8093 did not recover to running/listening' }

    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/' -TimeoutSec 20
    if ([int]$response.StatusCode -ne 200) { throw '8093 HTTP recovery check failed' }

    $listen8768After = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
    if ($listen8768After.OwningProcess -ne $listen8768Before.OwningProcess) {
        throw '8768 PID changed during 8093 recovery'
    }

    [ordered]@{
        ok = $true
        service = $service.Status.ToString()
        http_status = [int]$response.StatusCode
        listener_pid = $listener.OwningProcess
        ws8768_pid_before = $listen8768Before.OwningProcess
        ws8768_pid_after = $listen8768After.OwningProcess
        backup = $backupRoot
    } | ConvertTo-Json -Depth 4
}
catch {
    if ($installed -and (Test-Path -LiteralPath $backup)) {
        Copy-Item -LiteralPath $backup -Destination $target -Force
    }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    }
    catch { }
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    }
    catch { }
    throw
}
