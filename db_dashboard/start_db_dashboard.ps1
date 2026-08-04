param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8890
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:BF_DB_DASHBOARD_HOST = $HostName
$env:BF_DB_DASHBOARD_PORT = "$Port"
$env:GL02_PGHOST = "127.0.0.1"
$env:GL02_PGPORT = "15432"
$env:GL02_PGDATABASE = "bf_trend"
$env:GL02_PGUSER = "gl02_sync"
$env:GL02_PGPASSWORD = "gl02_local_sync"

& ".\.venv\Scripts\python.exe" -u ".\db_dashboard\server.py"
