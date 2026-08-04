param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8890
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot

$env:GL02_PGHOST = "127.0.0.1"
$env:GL02_PGPORT = "15432"
$env:GL02_PGDATABASE = "bf_trend"
$env:GL02_PGUSER = "gl02_sync"
$env:GL02_PGPASSWORD = "gl02_local_sync"
$env:BF_DB_DASHBOARD_HOST = $HostName
$env:BF_DB_DASHBOARD_PORT = [string]$Port
$env:BF_DB_DASHBOARD_SYNC_INTERVAL_SECONDS = "300"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

Set-Location $ProjectRoot
& $Python .\db_dashboard\server.py
