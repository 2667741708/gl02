$ErrorActionPreference = "Continue"
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
$LogPath = Join-Path $LogDir ("history_sync_90d_pg_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

& $Python (Join-Path $ScriptRoot "src\sync_from_243_pg.py") `
    --days 90 `
    --chunk-hours 12 `
    --batch-size 4 `
    --max-workers 1 `
    --retries 3 `
    --retry-sleep 8 `
    --source-mode processed `
    --skip-schema `
    *>&1 | Tee-Object -FilePath $LogPath
