$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$wsServiceName = 'BFV4PreviewWs8768'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$source = Join-Path $root 'logs\deploy_backups\diagnosis_ai_analysis_20260805_231812\高炉前端数据__智能助手__backend__ollama_proxy_server.py'
$target = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$recoveryBackup = Join-Path $root "logs\deploy_backups\8093_proxy_emergency_restore_$stamp"

foreach ($required in @($manager, $configPath, $source, $target)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "missing restore input: $required" }
}
if (Select-String -LiteralPath $source -Pattern 'cross_source_plan' -Quiet) {
    throw 'selected stable backup contains the unavailable cross-source dependency'
}

$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$listen8768Before = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
if ($wsBefore.Status -ne 'Running') { throw '8768 must be running before restore' }

New-Item -ItemType Directory -Path $recoveryBackup -Force | Out-Null
Copy-Item -LiteralPath $target -Destination (Join-Path $recoveryBackup 'broken_ollama_proxy_server.py') -Force

$service = Get-Service -Name $serviceName -ErrorAction Stop
if ($service.Status -ne 'Stopped') {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath
    if ($LASTEXITCODE -ne 0) { throw 'failed to stop 8093 before stable restore' }
}

$temporary = "$target.codex-$stamp.tmp"
Copy-Item -LiteralPath $source -Destination $temporary -Force
Move-Item -LiteralPath $temporary -Destination $target -Force
& 'C:\Program Files\Python311\python.exe' -m py_compile $target
if ($LASTEXITCODE -ne 0) { throw 'restored proxy syntax validation failed' }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath
if ($LASTEXITCODE -ne 0) { throw 'failed to start restored 8093 proxy' }

$deadline = [DateTime]::UtcNow.AddSeconds(60)
do {
    $service = Get-Service -Name $serviceName -ErrorAction Stop
    $listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue
    if ($service.Status -eq 'Running' -and $listener) { break }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
if ($service.Status -ne 'Running' -or -not $listener) { throw 'restored 8093 did not become running/listening' }

$response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/' -TimeoutSec 20
if ([int]$response.StatusCode -ne 200) { throw 'restored 8093 HTTP check failed' }
$listen8768After = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
if ($listen8768After.OwningProcess -ne $listen8768Before.OwningProcess) { throw '8768 PID changed during restore' }

[ordered]@{
    ok = $true
    restored_from = $source
    recovery_backup = $recoveryBackup
    service = $service.Status.ToString()
    http_status = [int]$response.StatusCode
    listener_pid = $listener.OwningProcess
    ws8768_pid_before = $listen8768Before.OwningProcess
    ws8768_pid_after = $listen8768After.OwningProcess
} | ConvertTo-Json -Depth 4
