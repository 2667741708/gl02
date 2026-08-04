param(
    [switch]$AsSystem,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DbDir = Join-Path $ProjectRoot "db_sync_storage"
$DiagDir = Join-Path $ProjectRoot "auto_diagnosis_service"
$HiddenLauncher = Join-Path $ProjectRoot "tools\run_hidden_ps1.vbs"
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$InstallLog = Join-Path $LogDir ("local_autoguard_tasks_install_{0}.log" -f (Get-Date -Format "yyyyMMddHHmmss"))

function Write-InstallLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath $InstallLog -Append
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Set-EnvDefault {
    param(
        [string]$Name,
        [string]$Value,
        [string]$Scope
    )
    [Environment]::SetEnvironmentVariable($Name, $Value, $Scope)
    Set-Item -Path "Env:$Name" -Value $Value
    if ($Name -like "*PASSWORD*") {
        Write-InstallLog "$Name=<set len=$($Value.Length)> scope=$Scope"
    } else {
        Write-InstallLog "$Name=$Value scope=$Scope"
    }
}

function Stop-MatchingProcesses {
    param([string[]]$Patterns)
    Get-CimInstance Win32_Process |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return $false }
            foreach ($pattern in $Patterns) {
                if ($cmd -match [regex]::Escape($pattern)) { return $true }
            }
            return $false
        } |
        ForEach-Object {
            Write-InstallLog ("stop_existing pid={0} command={1}" -f $_.ProcessId, $_.CommandLine)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Register-LocalTask {
    param(
        [string]$TaskPath,
        [string]$TaskName,
        [string]$Runner,
        [int]$ExecutionTimeLimitMinutes
    )

    if (-not (Test-Path -LiteralPath $Runner)) {
        throw "Runner not found: $Runner"
    }
    if (-not (Test-Path -LiteralPath $HiddenLauncher)) {
        throw "Hidden launcher not found: $HiddenLauncher"
    }

    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument ('//B //Nologo "{0}" "{1}"' -f $HiddenLauncher, $Runner)

    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 5) `
        -RepetitionDuration (New-TimeSpan -Days 3650)

    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $ExecutionTimeLimitMinutes) `
        -StartWhenAvailable `
        -Hidden

    $registerArgs = @{
        TaskPath = $TaskPath
        TaskName = $TaskName
        Action = $action
        Trigger = $trigger
        Settings = $settings
        Force = $true
    }

    if ($AsSystem) {
        if (-not (Test-IsAdministrator)) {
            throw "Registering as SYSTEM requires an elevated PowerShell session. Re-run as Administrator or omit -AsSystem."
        }
        $registerArgs.Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
        Write-InstallLog "register_task task=$TaskPath$TaskName principal=SYSTEM"
    } else {
        $registerArgs.Description = "Local GL02 V3 automatic guard task. Runs under the current Windows user and uses User-scope local Docker PostgreSQL environment variables."
        Write-InstallLog "register_task task=$TaskPath$TaskName principal=current_user"
    }

    Register-ScheduledTask @registerArgs | Out-Null

    if (-not $NoStart) {
        Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    }

    $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName
    Write-InstallLog ("registered task={0}{1} state={2} last_result={3} next_run={4}" -f $TaskPath, $TaskName, $task.State, $info.LastTaskResult, $info.NextRunTime)
}

Write-InstallLog "install_start mode=$(if ($AsSystem) { 'SYSTEM' } else { 'current_user' })"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python venv not found: $python"
}

$envScope = if ($AsSystem) { "Machine" } else { "User" }
Set-EnvDefault "PYTHON_EXE" $python $envScope
Set-EnvDefault "GL02_PGHOST" "127.0.0.1" $envScope
Set-EnvDefault "GL02_PGPORT" "15432" $envScope
Set-EnvDefault "GL02_PGDATABASE" "bf_trend" $envScope
Set-EnvDefault "GL02_PGUSER" "gl02_sync" $envScope
Set-EnvDefault "GL02_PGPASSWORD" "gl02_local_sync" $envScope
Set-EnvDefault "PSPACE_SERVER" "10.22.181.243" $envScope
Set-EnvDefault "PSPACE_PORT" "8889" $envScope
Set-EnvDefault "BF_SKIP_ZERO_AUDIT" "1" $envScope

$ollama = [Environment]::GetEnvironmentVariable("OLLAMA_BASE_URL", "User")
if (-not $ollama) { $ollama = "http://10.30.220.12:11434" }
Set-EnvDefault "OLLAMA_BASE_URL" $ollama $envScope

$model = [Environment]::GetEnvironmentVariable("BF_LLM_MODEL", "User")
if (-not $model) { $model = "chiqiong-blast-furnace:latest" }
Set-EnvDefault "BF_LLM_MODEL" $model $envScope

Stop-MatchingProcesses @("sync_watchdog.py", "run_sync_watchdog.ps1", "auto_guard_once.py", "run_auto_diagnosis_once.ps1")

foreach ($lock in @(
    (Join-Path $DbDir "logs\sync_watchdog.lock"),
    (Join-Path $DiagDir "logs\auto_guard_once.lock")
)) {
    if (Test-Path -LiteralPath $lock) {
        Remove-Item -LiteralPath $lock -Force
        Write-InstallLog "removed_stale_lock $lock"
    }
}

Register-LocalTask `
    -TaskPath "\GL02SensorSync\" `
    -TaskName "Watchdog" `
    -Runner (Join-Path $DbDir "run_sync_watchdog.ps1") `
    -ExecutionTimeLimitMinutes 30

Register-LocalTask `
    -TaskPath "\GL02AutoDiagnosis\" `
    -TaskName "RunOnce" `
    -Runner (Join-Path $DiagDir "run_auto_diagnosis_once.ps1") `
    -ExecutionTimeLimitMinutes 20

Write-InstallLog "install_done"

[PSCustomObject]@{
    ok = $true
    mode = if ($AsSystem) { "SYSTEM" } else { "current_user" }
    env_scope = $envScope
    database = "127.0.0.1:15432/bf_trend"
    sync_watchdog_task = "\GL02SensorSync\Watchdog"
    auto_diagnosis_task = "\GL02AutoDiagnosis\RunOnce"
    install_log = $InstallLog
} | ConvertTo-Json -Depth 4
