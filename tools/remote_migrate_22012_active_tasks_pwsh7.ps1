[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.ToString() -ne '7.6.4') {
    throw 'This migration must run under PowerShell 7.6.4 Core.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ProgressPreference = 'SilentlyContinue'

$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\OPS-22012-PWSH7-ALL-20260811'
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-tasks" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$Targets = @(
    [ordered]@{
        id = 'AutoDiagnosisRunOnce'
        task_path = '\GL02AutoDiagnosis\'
        task_name = 'RunOnce'
        payload = 'F:\高炉炼铁项目-real-sensor-v2_V3\auto_diagnosis_service\run_auto_diagnosis_once.ps1'
        staged = Join-Path $StageRoot 'run_auto_diagnosis_once.ps1'
        validate_args = @('-ValidateOnly')
    },
    [ordered]@{
        id = 'SensorSyncWatchdog'
        task_path = '\GL02SensorSync\'
        task_name = 'Watchdog'
        payload = 'F:\高炉炼铁项目-real-sensor-v2_V3\db_sync_storage\run_sync_watchdog.ps1'
        staged = Join-Path $StageRoot 'run_sync_watchdog.ps1'
        validate_args = @('-ValidateOnly')
    },
    [ordered]@{
        id = 'Preview8094'
        task_path = '\BlastFurnaceServices\'
        task_name = 'V3AutoPreviewProxy8094'
        payload = Join-Path $Root 'tools\run_22012_8094_preview.ps1'
        staged = Join-Path $StageRoot 'run_22012_8094_preview.ps1'
        validate_args = @('-ValidateOnly')
    }
)

function Get-StateName($Task) {
    switch ([int]$Task.State) {
        1 { return 'Disabled' }
        2 { return 'Queued' }
        3 { return 'Ready' }
        4 { return 'Running' }
        default { return "Unknown:$([int]$Task.State)" }
    }
}

function Get-ExactTask($Target) {
    $matches = @(Get-ScheduledTask -TaskName $Target.task_name -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskPath -eq $Target.task_path })
    if ($matches.Count -ne 1) { throw "Task identity mismatch: $($Target.task_path)$($Target.task_name)" }
    return $matches[0]
}

function Wait-TaskIdle($Target, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-StateName (Get-ExactTask $Target)) -ne 'Running') { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Task did not become idle: $($Target.id)"
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Install-Atomically([string]$Source, [string]$Destination) {
    $temporary = "$Destination.$PID.pwsh7.tmp"
    $replaceBackup = "$Destination.$PID.pwsh7.replace.bak"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    try {
        [IO.File]::Replace($temporary, $Destination, $replaceBackup, $true)
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
    }
}

function Assert-Syntax([string]$Path) {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "PowerShell parse failed for ${Path}: $($errors[0].Message)" }
}

function Invoke-ValidateOnly($Target) {
    $arguments = @('-NoLogo', '-NoProfile', '-File', [string]$Target.payload) + @($Target.validate_args)
    $output = @(& $PwshPath @arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "ValidateOnly failed for $($Target.id): $($output -join ' ')"
    }
    return @($output)
}

function New-PreservedTaskAction([string]$Arguments, [string]$WorkingDirectory) {
    if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        return New-ScheduledTaskAction -Execute $PwshPath -Argument $Arguments
    }
    return New-ScheduledTaskAction -Execute $PwshPath -Argument $Arguments -WorkingDirectory $WorkingDirectory
}

if (-not (Test-Path -LiteralPath $PwshPath -PathType Leaf)) { throw 'PowerShell 7.6.4 is unavailable.' }
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$Results = [System.Collections.Generic.List[object]]::new()

foreach ($target in $Targets) {
    if (-not (Test-Path -LiteralPath $target.staged -PathType Leaf)) { throw "Staged file missing: $($target.staged)" }
    if (-not (Test-Path -LiteralPath $target.payload -PathType Leaf)) { throw "Payload missing: $($target.payload)" }
    Assert-Syntax $target.staged

    $task = Get-ExactTask $target
    $stateBefore = Get-StateName $task
    $wasEnabled = $stateBefore -ne 'Disabled'
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) { throw "Expected one action for $($target.id)" }
    $oldAction = $actions[0]
    $oldLeaf = [IO.Path]::GetFileName(([string]$oldAction.Execute).Trim('"'))
    if ($oldLeaf -inotmatch '^(?:powershell|pwsh)\.exe$') { throw "Unexpected task runtime for $($target.id)" }
    if ([string]$oldAction.Arguments -notlike "*$($target.payload)*") { throw "Task payload mismatch for $($target.id)" }

    $targetBackup = Join-Path $BackupRoot $target.id
    New-Item -ItemType Directory -Path $targetBackup -Force | Out-Null
    $taskXml = Export-ScheduledTask -TaskPath $target.task_path -TaskName $target.task_name
    Write-Utf8NoBom (Join-Path $targetBackup 'task_before.xml') $taskXml
    Copy-Item -LiteralPath $target.payload -Destination (Join-Path $targetBackup 'payload_before.ps1') -Force

    $rollbackApplied = $false
    try {
        $isLongRunning8094 = $target.id -eq 'Preview8094' -and $stateBefore -eq 'Running'
        if ($wasEnabled -and -not $isLongRunning8094) {
            Disable-ScheduledTask -TaskPath $target.task_path -TaskName $target.task_name | Out-Null
            Wait-TaskIdle $target
        }
        Install-Atomically $target.staged $target.payload
        Assert-Syntax $target.payload
        $validation = Invoke-ValidateOnly $target

        $desiredArguments = ([string]$oldAction.Arguments) -replace '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
        $newAction = New-PreservedTaskAction $desiredArguments ([string]$oldAction.WorkingDirectory)
        Set-ScheduledTask -TaskPath $target.task_path -TaskName $target.task_name -Action $newAction | Out-Null
        if ($wasEnabled -and -not $isLongRunning8094) {
            Enable-ScheduledTask -TaskPath $target.task_path -TaskName $target.task_name | Out-Null
        }

        $after = Get-ExactTask $target
        $afterAction = @($after.Actions)[0]
        if ([string]$afterAction.Execute -ine $PwshPath) { throw "Task runtime verification failed for $($target.id)" }
        $Results.Add([ordered]@{
            id = $target.id
            changed = ([string]$oldAction.Execute -ine $PwshPath) -or ((Get-FileHash -LiteralPath $target.staged -Algorithm SHA256).Hash -ine (Get-FileHash -LiteralPath (Join-Path $targetBackup 'payload_before.ps1') -Algorithm SHA256).Hash)
            state_before = $stateBefore
            state_after = Get-StateName $after
            action_before = [string]$oldAction.Execute
            action_after = [string]$afterAction.Execute
            payload_sha256 = (Get-FileHash -LiteralPath $target.payload -Algorithm SHA256).Hash
            validate_output = @($validation)
            backup = $targetBackup
            rollback_applied = $false
        })
    } catch {
        $failure = $_.Exception.Message
        try {
            Copy-Item -LiteralPath (Join-Path $targetBackup 'payload_before.ps1') -Destination $target.payload -Force
            Register-ScheduledTask -TaskPath $target.task_path -TaskName $target.task_name -Xml $taskXml -Force | Out-Null
            $rollbackApplied = $true
        } catch {
            $failure = "$failure; rollback_failed=$($_.Exception.Message)"
        }
        [ordered]@{
            schema = 'ops.22012.active-tasks-pwsh7-migration.result.v1'
            ok = $false
            failed_target = $target.id
            error = $failure
            rollback_applied = $rollbackApplied
            backup_root = $BackupRoot
            completed = @($Results)
        } | ConvertTo-Json -Depth 10
        exit 2
    }
}

[ordered]@{
    schema = 'ops.22012.active-tasks-pwsh7-migration.result.v1'
    ok = $true
    powershell_version = $PSVersionTable.PSVersion.ToString()
    backup_root = $BackupRoot
    results = @($Results)
} | ConvertTo-Json -Depth 10
