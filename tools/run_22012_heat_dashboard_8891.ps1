$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
$server = "$root\db_dashboard\server.py"
$logDir = "$root\logs"
$log = "$logDir\heat_dashboard_8891.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Reuse the machine-scoped GL02 read-only connection without printing its values.
foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:BF_DB_DASHBOARD_HOST = "0.0.0.0"
$env:BF_DB_DASHBOARD_PORT = "8891"
$env:BF_DB_DASHBOARD_SYNC_INTERVAL_SECONDS = "0"
$env:IMES_OPS_DB_HOST = "10.10.181.195"
$env:IMES_OPS_DB_PORT = "5432"
$env:IMES_LAB_DB_HOST = "10.10.181.195"
$env:IMES_LAB_DB_PORT = "5432"

if (-not (Test-Path -LiteralPath $server)) {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') missing server: $server"
    exit 2
}

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting standalone heat dashboard on 8891"
    Set-Location -LiteralPath $root
    & "C:\Program Files\Python311\python.exe" -X utf8 -u $server >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt dashboard exited with code $LASTEXITCODE; restart in 5s"
    Start-Sleep -Seconds 5
}
