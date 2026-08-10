param(
    [double]$Minutes = 10,
    [int]$BatchSize = 115,
    [int]$MaxWorkers = 1,
    [int]$RawMaxValues = 200000,
    [int]$RetentionDays = 30,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "PSPACE_SDK_ROOT") {
    if (-not (Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue)) {
        $machineValue = [Environment]::GetEnvironmentVariable($name, "Machine")
        if ($machineValue) {
            Set-Item -Path "Env:$name" -Value $machineValue
        }
    }
}

if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    throw "Missing GL02_PGUSER/GL02_PGPASSWORD. Set PostgreSQL credentials before raw 5s sync."
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
}

$ArgsList = @(
    (Join-Path $ScriptRoot "src\sync_raw_5s_from_243_pg.py"),
    "--minutes", "$Minutes",
    "--batch-size", "$BatchSize",
    "--max-workers", "$MaxWorkers",
    "--raw-max-values", "$RawMaxValues",
    "--retention-days", "$RetentionDays"
)
if ($DryRun) {
    $ArgsList += "--dry-run"
}

Set-Location $ProjectRoot
& $Python -X utf8 @ArgsList
exit $LASTEXITCODE
