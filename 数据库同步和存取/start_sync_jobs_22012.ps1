$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
$LogDir = Join-Path $ScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    throw "GL02 PostgreSQL environment variables are missing. Run install_postgresql_22012.ps1 first."
}

$historyScript = Join-Path $ScriptRoot "run_history_sync_pg_bg.ps1"
$realtimeScript = Join-Path $ScriptRoot "run_realtime_sync_pg_bg.ps1"
$history = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $historyScript) -WindowStyle Hidden -PassThru
$realtime = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $realtimeScript) -WindowStyle Hidden -PassThru

[PSCustomObject]@{
    history_pid = $history.Id
    history_script = $historyScript
    realtime_pid = $realtime.Id
    realtime_script = $realtimeScript
} | ConvertTo-Json -Depth 3
