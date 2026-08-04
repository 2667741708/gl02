param(
    [string]$RemoteRoot = "F:\高炉炼铁项目-real-sensor-v2_V3",
    [string]$HostAddress = "10.30.220.12",
    [switch]$SkipWebSocketChecks
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
$RemoteScript = Join-Path $ToolsDir "remote_check_22012_data_chain.ps1"
$WsCheck = Join-Path $ToolsDir "check_v3_ws_bridge_python.py"

Write-Host "[check] Checking server-side ports, tasks, HTTP APIs and database freshness..."
& $Python $RemoteExec `
    --allow-agents-password `
    --workdir $RemoteRoot `
    --timeout 240 `
    --script $RemoteScript
if ($LASTEXITCODE -ne 0) {
    throw "Remote data-chain check failed with exit code $LASTEXITCODE"
}

if (-not $SkipWebSocketChecks) {
    foreach ($port in @(8768, 8767)) {
        $url = "ws://$HostAddress`:$port"
        Write-Host "[check] Checking $url ..."
        & $Python $WsCheck --url $url --timeout 20 --min-diagnosis-history 1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "WebSocket check failed for $url"
        }
    }
}

Write-Host "[check] Done."
