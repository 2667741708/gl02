$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "PSPACE_SDK_ROOT") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
if (-not $env:PSPACE_SERVER) { $env:PSPACE_SERVER = "10.22.181.243" }
if (-not $env:PSPACE_PORT) { $env:PSPACE_PORT = "8889" }

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
if (-not $Python) {
    $Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "User")
}
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$LogPath = Join-Path $LogDir ("sync_watchdog_runner_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

& $Python -X utf8 (Join-Path $ScriptRoot "src\sync_watchdog.py") `
    --stale-minutes 6 `
    --recent-hours 12 `
    --history-days 90 `
    --history-bucket-minutes 60 `
    --min-gap-minutes 5 `
    --backfill-max-ranges 3 `
    --backfill-max-hours 1 `
    --backfill-chunk-hours 0.2 `
    --backfill-timeout-seconds 900 `
    --batch-size 115 `
    --max-workers 1 `
    --lock-stale-minutes 30 `
    *>&1 | Tee-Object -FilePath $LogPath -Append

exit $LASTEXITCODE
