$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ScriptRoot "logs"
$Runner = Join-Path $ScriptRoot "run_auto_diagnosis_once.ps1"
$InstallLog = Join-Path $LogDir ("auto_diagnosis_task_install_{0}.log" -f (Get-Date -Format "yyyyMMddHHmmss"))
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-InstallLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath $InstallLog -Append
}

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Runner not found: $Runner"
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $Python) {
    [Environment]::SetEnvironmentVariable("PYTHON_EXE", $Python, "Machine")
    Set-Item -Path "Env:PYTHON_EXE" -Value $Python
    Write-InstallLog "PYTHON_EXE=$Python"
}

foreach ($name in "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        throw "Missing machine-level environment variable $name"
    }
}

[Environment]::SetEnvironmentVariable("GL02_PGHOST", "127.0.0.1", "Machine")
[Environment]::SetEnvironmentVariable("GL02_PGPORT", "5432", "Machine")
[Environment]::SetEnvironmentVariable("GL02_PGDATABASE", "bf_trend", "Machine")
[Environment]::SetEnvironmentVariable("PSPACE_SERVER", "10.22.181.243", "Machine")
[Environment]::SetEnvironmentVariable("PSPACE_PORT", "8889", "Machine")

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match 'auto_guard_once.py' -or
            $_.CommandLine -match 'run_auto_diagnosis_once.ps1'
        )
    } |
    ForEach-Object {
        Write-InstallLog ("stop_existing_auto_guard pid={0}" -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$LockPath = Join-Path $LogDir "auto_guard_once.lock"
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

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20) `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

Register-ScheduledTask `
    -TaskPath "\GL02AutoDiagnosis\" `
    -TaskName "RunOnce" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

Start-ScheduledTask -TaskPath "\GL02AutoDiagnosis\" -TaskName "RunOnce"

$Task = Get-ScheduledTask -TaskPath "\GL02AutoDiagnosis\" -TaskName "RunOnce"
$Info = Get-ScheduledTaskInfo -TaskPath "\GL02AutoDiagnosis\" -TaskName "RunOnce"
Write-InstallLog ("registered state={0} last_result={1} next_run={2}" -f $Task.State, $Info.LastTaskResult, $Info.NextRunTime)
Write-InstallLog "install_done"

[PSCustomObject]@{
    task = "\GL02AutoDiagnosis\RunOnce"
    runner = $Runner
    python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
    next_run = $Info.NextRunTime
} | ConvertTo-Json -Depth 3
