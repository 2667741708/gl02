$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ScriptRoot "logs"
$Runner = Join-Path $ScriptRoot "run_sync_watchdog.ps1"
$InstallLog = Join-Path $LogDir ("sync_watchdog_install_{0}.log" -f (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-InstallLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath $InstallLog -Append
}

Write-InstallLog "install_start"

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $Python) {
    [Environment]::SetEnvironmentVariable("PYTHON_EXE", $Python, "Machine")
    Set-Item -Path "Env:PYTHON_EXE" -Value $Python
    Write-InstallLog "PYTHON_EXE=$Python"
}

if (-not [Environment]::GetEnvironmentVariable("GL02_PGHOST", "Machine")) {
    [Environment]::SetEnvironmentVariable("GL02_PGHOST", "127.0.0.1", "Machine")
}
if (-not [Environment]::GetEnvironmentVariable("GL02_PGPORT", "Machine")) {
    [Environment]::SetEnvironmentVariable("GL02_PGPORT", "5432", "Machine")
}
if (-not [Environment]::GetEnvironmentVariable("GL02_PGDATABASE", "Machine")) {
    [Environment]::SetEnvironmentVariable("GL02_PGDATABASE", "bf_trend", "Machine")
}
if (-not [Environment]::GetEnvironmentVariable("PSPACE_SERVER", "Machine")) {
    [Environment]::SetEnvironmentVariable("PSPACE_SERVER", "10.22.181.243", "Machine")
}
if (-not [Environment]::GetEnvironmentVariable("PSPACE_PORT", "Machine")) {
    [Environment]::SetEnvironmentVariable("PSPACE_PORT", "8889", "Machine")
}

foreach ($name in "GL02_PGUSER", "GL02_PGPASSWORD") {
    if (-not [Environment]::GetEnvironmentVariable($name, "Machine")) {
        throw "Missing machine-level environment variable $name"
    }
}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'sync_watchdog.py' -or
            $_.CommandLine -match 'run_sync_watchdog.ps1'
        )
    } |
    ForEach-Object {
        Write-InstallLog ("stop_existing_watchdog pid={0}" -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$LockPath = Join-Path $LogDir "sync_watchdog.lock"
if (Test-Path -LiteralPath $LockPath) {
    Remove-Item -LiteralPath $LockPath -Force
    Write-InstallLog "removed_stale_lock"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $Runner)

$Trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

try {
    $Settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -StartWhenAvailable

    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

    Register-ScheduledTask `
        -TaskPath "\GL02SensorSync\" `
        -TaskName "Watchdog" `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Force | Out-Null

    Start-ScheduledTask -TaskPath "\GL02SensorSync\" -TaskName "Watchdog"

    $Task = Get-ScheduledTask -TaskPath "\GL02SensorSync\" -TaskName "Watchdog"
    $Info = Get-ScheduledTaskInfo -TaskPath "\GL02SensorSync\" -TaskName "Watchdog"
    Write-InstallLog ("registered state={0} last_result={1} next_run={2}" -f $Task.State, $Info.LastTaskResult, $Info.NextRunTime)
    Write-InstallLog "install_done"
} catch {
    Write-InstallLog ("install_error {0}" -f $_.Exception.Message)
    throw
}
