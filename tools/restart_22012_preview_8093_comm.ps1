param(
    [string]$RemoteRoot = "F:\高炉炼铁项目-real-sensor-v2_V3",
    [string]$HostAddress = "10.30.220.12",
    [int]$WsPort = 8768,
    [int]$HttpPort = 8093,
    [switch]$SkipWebSocketCheck
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ToolsDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$RemoteExec = Join-Path $ToolsDir "remote_22012_exec.py"
$RemoteScript = Join-Path $ToolsDir "remote_recover_22012_preview_comm.ps1"
$WsCheck = Join-Path $ToolsDir "check_v3_ws_bridge_python.py"

if (-not (Test-Path -LiteralPath $RemoteExec)) { throw "Missing $RemoteExec" }
if (-not (Test-Path -LiteralPath $RemoteScript)) { throw "Missing $RemoteScript" }
if (-not (Test-Path -LiteralPath $WsCheck)) { throw "Missing $WsCheck" }

Write-Host "[recover] Starting/checking 220.12 preview communication guards..."
& $Python $RemoteExec `
    --allow-agents-password `
    --workdir $RemoteRoot `
    --timeout 240 `
    --script $RemoteScript
if ($LASTEXITCODE -ne 0) {
    throw "Remote recovery script failed with exit code $LASTEXITCODE"
}

if (-not $SkipWebSocketCheck) {
    $wsUrl = "ws://$HostAddress`:$WsPort"
    Write-Host "[recover] Checking WebSocket $wsUrl ..."
    & $Python $WsCheck --url $wsUrl --timeout 20 --min-diagnosis-history 1
    if ($LASTEXITCODE -ne 0) {
        throw "WebSocket check failed for $wsUrl"
    }
}

Write-Host "[recover] Checking 8093 database/API status..."
try {
    $apiUrl = "http://$HostAddress`:$HttpPort/api/automation/status"
    $status = (Invoke-WebRequest -Uri $apiUrl -UseBasicParsing -TimeoutSec 20).Content | ConvertFrom-Json
    [PSCustomObject]@{
        ok = $status.ok
        database_ok = $status.database_ok
        latest_data_ts = $status.latest_data_ts
        latest_diagnosis_ts = $status.latest.diagnosis_ts
        source_lag_seconds = $status.latest.source_lag_seconds
        quality_status = $status.latest_quality.status
    } | Format-List
} catch {
    throw "8093 API check failed: $($_.Exception.Message)"
}

Write-Host "[recover] Done. Refresh http://$HostAddress`:$HttpPort/#diagnosis after this check passes."
