$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $PSScriptRoot
$taskPath = '\BlastFurnaceServices\'
$taskName = 'SiV20ScheduledShadowPrediction'
$runner = Join-Path $root 'tools\run_22012_si_v20_schedule_dispatcher.ps1'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$backupRoot = Join-Path $root ("logs\deploy_backups\si_v20_schedule_task_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$backupXml = Join-Path $backupRoot 'task.before.xml'

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Schedule dispatcher runner is unavailable' }
if (-not (Test-Path -LiteralPath $pwsh -PathType Leaf)) { throw 'PowerShell 7 is unavailable' }
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$existing = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$existingXml = $null
if ($existing) {
    $existingXml = Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    [IO.File]::WriteAllText($backupXml, $existingXml, [Text.UTF8Encoding]::new($true))
}

$now = Get-Date
$startAt = $now.AddMinutes(1).Date.AddHours($now.AddMinutes(1).Hour).AddMinutes($now.AddMinutes(1).Minute).AddSeconds(5)
$action = New-ScheduledTaskAction `
    -Execute $pwsh `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $startAt `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 1)

try {
    Register-ScheduledTask `
        -TaskPath $taskPath `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Dispatch configurable V20 shadow predictions every minute; audit writes only.' `
        -Force | Out-Null
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    if ([int]$task.Settings.MultipleInstances -ne 2) { throw 'Task overlap policy is not IgnoreNew' }
} catch {
    $registrationError = $_
    if ($existingXml) {
        Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Xml $existingXml -Force | Out-Null
    } else {
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    throw $registrationError
}

$taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
[ordered]@{
    schema = 'ops.si-v20.schedule-task-registration.v1'
    task_path = $taskPath
    task_name = $taskName
    state = $task.State.ToString()
    next_run_time = $taskInfo.NextRunTime.ToString('o')
    dispatcher_interval = 'PT1M'
    multiple_instances = $task.Settings.MultipleInstances.ToString()
    principal = $task.Principal.UserId
    backup_xml = if ($existingXml) { $backupXml } else { $null }
    configuration_table = 'bf_assistant.si_v20_prediction_schedule'
    audit_table = 'bf_assistant.si_v20_prediction_audit'
    writes_prediction_audit_only = $true
} | ConvertTo-Json -Depth 5
