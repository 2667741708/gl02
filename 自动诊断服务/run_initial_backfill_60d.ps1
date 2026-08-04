$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
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

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$LogPath = Join-Path $LogDir ("initial_backfill_60d_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

& $Python -X utf8 (Join-Path $ScriptRoot "initial_backfill_60d.py") `
    --days 60 `
    --baseline-days 30 `
    *>&1 | Tee-Object -FilePath $LogPath

exit $LASTEXITCODE
