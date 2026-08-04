param(
    [switch]$SkipPip,
    [switch]$RunHistory90d,
    [switch]$RunInitialDiagnosis60d,
    [switch]$InstallExternalReadOnly,
    [string]$ClientCidr = $env:DB_CLIENT_CIDR
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DbDir = Join-Path $ProjectRoot "db_sync_storage"
$DiagDir = Join-Path $ProjectRoot "auto_diagnosis_service"
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Step {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath (Join-Path $LogDir "install_22012_autoguard.log") -Append
}

function Set-MachineDefault {
    param([string]$Name, [string]$Value)
    if (-not [Environment]::GetEnvironmentVariable($Name, "Machine")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Machine")
    }
    Set-Item -Path "Env:$Name" -Value ([Environment]::GetEnvironmentVariable($Name, "Machine"))
}

Write-Step "install_start"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $BasePython = if ($env:PYTHON_EXE -and (Test-Path -LiteralPath $env:PYTHON_EXE)) { $env:PYTHON_EXE } else { "python" }
    Write-Step "create_venv base=$BasePython"
    & $BasePython -m venv (Join-Path $ProjectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
}

[Environment]::SetEnvironmentVariable("PYTHON_EXE", $Python, "Machine")
Set-Item -Path "Env:PYTHON_EXE" -Value $Python

if (-not $SkipPip) {
    Write-Step "install_python_requirements"
    & $Python -m pip install -r (Join-Path $ProjectRoot "requirements-local.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

Set-MachineDefault "GL02_PGHOST" "127.0.0.1"
Set-MachineDefault "GL02_PGPORT" "5432"
Set-MachineDefault "GL02_PGDATABASE" "bf_trend"
Set-MachineDefault "PSPACE_SERVER" "10.22.181.243"
Set-MachineDefault "PSPACE_PORT" "8889"

foreach ($name in "GL02_PGUSER", "GL02_PGPASSWORD") {
    if (-not [Environment]::GetEnvironmentVariable($name, "Machine")) {
        throw "Missing machine-level environment variable $name"
    }
}

$svc = Get-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Step ("postgres_service status={0}" -f $svc.Status)
    Set-Service -Name "postgresql-x64-16" -StartupType Automatic
    if ($svc.Status -ne "Running") {
        try {
            Start-Service -Name "postgresql-x64-16"
            Write-Step "postgres_service_started"
        } catch {
            Write-Step ("postgres_service_start_warning {0}" -f $_.Exception.Message)
        }
    }
} else {
    Write-Step "postgres_service_not_found"
}

Write-Step "init_sensor_schema"
& $Python -X utf8 (Join-Path $DbDir "src\init_pg.py")
if ($LASTEXITCODE -ne 0) { throw "init_pg.py failed" }

Write-Step "init_diagnosis_schema"
$initDiag = "import sys; sys.path.insert(0, r'$DiagDir'); from store import DiagnosisStore; DiagnosisStore().ensure_schema(); print('diagnosis_schema_ok')"
& $Python -X utf8 -c $initDiag
if ($LASTEXITCODE -ne 0) { throw "diagnosis schema initialization failed" }

Write-Step "install_sync_watchdog_task"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $DbDir "install_sync_watchdog_task.ps1")
if ($LASTEXITCODE -ne 0) { throw "install_sync_watchdog_task.ps1 failed" }

Write-Step "install_auto_diagnosis_task"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $DiagDir "install_auto_diagnosis_task.ps1")
if ($LASTEXITCODE -ne 0) { throw "install_auto_diagnosis_task.ps1 failed" }

if ($InstallExternalReadOnly) {
    Write-Step "setup_external_readonly_access"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $DbDir "setup_external_readonly_access.ps1") -ClientCidr $ClientCidr
    if ($LASTEXITCODE -ne 0) { throw "setup_external_readonly_access.ps1 failed" }
}

if ($RunHistory90d) {
    Write-Step "start_history_90d_backfill"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $DbDir "run_history_sync_pg_bg.ps1")) -WindowStyle Hidden | Out-Null
}

if ($RunInitialDiagnosis60d) {
    Write-Step "start_initial_diagnosis_60d_backfill"
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $DiagDir "run_initial_backfill_60d.ps1")) -WindowStyle Hidden | Out-Null
}

Write-Step "install_done"

[PSCustomObject]@{
    ok = $true
    python = $Python
    sync_watchdog_task = "\GL02SensorSync\Watchdog"
    auto_diagnosis_task = "\GL02AutoDiagnosis\RunOnce"
    history_backfill_started = [bool]$RunHistory90d
    diagnosis_backfill_started = [bool]$RunInitialDiagnosis60d
    external_readonly_configured = [bool]$InstallExternalReadOnly
} | ConvertTo-Json -Depth 4
