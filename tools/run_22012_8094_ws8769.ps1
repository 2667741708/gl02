$ErrorActionPreference = "Continue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$previewRoot = Join-Path $root "preview_8094_ws8769"
$bridge = Join-Path $previewRoot "local_pg_ws_bridge.py"
$engine = Join-Path $previewRoot "recommendation_engine"
$log = Join-Path $root "logs\preview_ws_8769.log"

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:BF_WS_HOST = "0.0.0.0"
$env:BF_WS_PORT = "8769"
$env:BF_WS_HISTORY_HOURS = "8"
$env:BF_WS_DIAGNOSIS_HISTORY_HOURS = "2"
$env:BF_WS_TICK_SECONDS = "30"
$env:BF_CHRONOS_BASE_URL = "http://127.0.0.1:8777"
$env:BF_RECOMMENDATION_ENGINE_DIR = $engine

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting isolated 8094 preview WebSocket 8769"
    Set-Location -LiteralPath $previewRoot
    & "C:\Program Files\Python311\python.exe" -X utf8 -u $bridge >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt preview WebSocket exited, restart in 5s"
    Start-Sleep -Seconds 5
}
