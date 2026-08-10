$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This migration must run under PowerShell 7 Core.'
}

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$taskDefinitions = @(
    [pscustomobject]@{
        TaskPath = '\GL02SensorSync\'
        TaskName = 'IMESRealtime'
        Runner = 'F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\run_22012_从IMES数据库同步.ps1'
        StagedRunner = $null
        RunnerHash = $null
    },
    [pscustomobject]@{
        TaskPath = '\BlastFurnaceServices\'
        TaskName = 'SiV20ScheduledShadowPrediction'
        Runner = Join-Path $root 'tools\run_22012_si_v20_schedule_dispatcher.ps1'
        StagedRunner = 'C:\Users\Administrator\AppData\Local\Temp\v20_schedule_runner_pwsh7.ps1'
        RunnerHash = '519FCD5562C2F66AB7C5BCE07FE2C5D931DFDF86C822064B3D4C538A82104195'
    }
)
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\v20_data_tasks_pwsh7_$stamp"

if (-not (Test-Path -LiteralPath $pwsh -PathType Leaf)) { throw 'PowerShell 7 is unavailable.' }
foreach ($definition in $taskDefinitions) {
    if (-not (Test-Path -LiteralPath $definition.Runner -PathType Leaf)) {
        throw "Runner is unavailable: $($definition.Runner)"
    }
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $definition.Runner, [ref]$tokens, [ref]$errors
    )
    if ($errors.Count) { throw "PowerShell 7 parse failed: $($definition.Runner)" }
    if ($definition.StagedRunner) {
        if (-not (Test-Path -LiteralPath $definition.StagedRunner -PathType Leaf)) {
            throw "Staged runner is unavailable: $($definition.StagedRunner)"
        }
        $hash = (Get-FileHash -LiteralPath $definition.StagedRunner -Algorithm SHA256).Hash
        if ($hash -ne $definition.RunnerHash) { throw 'Scheduled runner hash mismatch.' }
    }
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$taskSnapshots = @()
foreach ($definition in $taskDefinitions) {
    $task = Get-ScheduledTask -TaskPath $definition.TaskPath -TaskName $definition.TaskName -ErrorAction Stop
    $taskSnapshots += [pscustomobject]@{
        Definition = $definition
        Enabled = [int]$task.State -ne 1
        Action = $task.Actions[0]
    }
    Export-ScheduledTask -TaskPath $definition.TaskPath -TaskName $definition.TaskName |
        Set-Content -LiteralPath (Join-Path $backupRoot "$($definition.TaskName).xml") -Encoding UTF8
}
Copy-Item -LiteralPath $taskDefinitions[1].Runner -Destination (
    Join-Path $backupRoot 'run_22012_si_v20_schedule_dispatcher.ps1.bak'
) -Force

$rollbackApplied = $false
try {
    foreach ($snapshot in $taskSnapshots) {
        Disable-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName | Out-Null
        Stop-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName -ErrorAction SilentlyContinue
    }

    $temporary = "$($taskDefinitions[1].Runner).deploy_$stamp"
    Copy-Item -LiteralPath $taskDefinitions[1].StagedRunner -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $taskDefinitions[1].Runner -Force

    foreach ($snapshot in $taskSnapshots) {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $snapshot.Definition.Runner
        $action = New-ScheduledTaskAction -Execute $pwsh -Argument $arguments
        Set-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName -Action $action | Out-Null
        if ($snapshot.Enabled) {
            Enable-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName | Out-Null
        }
    }

    Start-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction'
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([int](Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction').State -eq 4) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Scheduled shadow task validation timed out.' }
        Start-Sleep -Milliseconds 250
    }
    $scheduledInfo = Get-ScheduledTaskInfo -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction'
    if ($scheduledInfo.LastTaskResult -ne 0) { throw "Scheduled shadow task failed: $($scheduledInfo.LastTaskResult)" }

    Start-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'IMESRealtime'
} catch {
    $migrationError = $_
    try {
        foreach ($snapshot in $taskSnapshots) {
            Stop-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName -ErrorAction SilentlyContinue
            Set-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName -Action $snapshot.Action | Out-Null
            if ($snapshot.Enabled) {
                Enable-ScheduledTask -TaskPath $snapshot.Definition.TaskPath -TaskName $snapshot.Definition.TaskName | Out-Null
            }
        }
        Copy-Item -LiteralPath (Join-Path $backupRoot 'run_22012_si_v20_schedule_dispatcher.ps1.bak') -Destination $taskDefinitions[1].Runner -Force
        $rollbackApplied = $true
    } catch {
        Write-Warning "Task-action rollback failed: $($_.Exception.Message)"
    }
    throw $migrationError
}

$results = foreach ($definition in $taskDefinitions) {
    $task = Get-ScheduledTask -TaskPath $definition.TaskPath -TaskName $definition.TaskName
    $action = $task.Actions[0]
    if ([IO.Path]::GetFileName([string]$action.Execute) -ieq 'powershell.exe') {
        throw "Legacy PowerShell remains configured for $($definition.TaskName)."
    }
    [ordered]@{
        task_path = $definition.TaskPath
        task_name = $definition.TaskName
        state = [int]$task.State
        action_execute = $action.Execute
        action_arguments = $action.Arguments
    }
}

[ordered]@{
    schema = 'ops.v20-data-tasks-pwsh7-migration.v1'
    migrated_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    rollback_applied = $rollbackApplied
    powershell_edition = $PSVersionTable.PSEdition
    powershell_version = $PSVersionTable.PSVersion.ToString()
    tasks = @($results)
} | ConvertTo-Json -Depth 6
