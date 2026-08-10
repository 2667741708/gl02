$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required'
}

$root = Split-Path -Parent $PSScriptRoot
$taskPath = '\BlastFurnaceServices\'
$taskName = 'SiV20StrictHourlyPrediction'
$runner = Join-Path $root 'tools\run_22012_si_v20_strict_hourly.ps1'
$backupRoot = Join-Path $root ("logs\deploy_backups\si_v20_strict_hourly_task_{0}" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$backupXml = Join-Path $backupRoot 'task.before.xml'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'

function Test-IgnoreNewPolicy {
    param($Value)
    return @('IgnoreNew', '2') -contains [string]$Value
}

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'Strict hourly runner is unavailable' }
if (-not (Test-Path -LiteralPath $pwsh -PathType Leaf)) { throw 'PowerShell 7 Core is unavailable' }
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$existing = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$existingXml = $null
if ($existing) {
    $existingXml = Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    [IO.File]::WriteAllText($backupXml, $existingXml, [Text.UTF8Encoding]::new($true))
}

$startAt = (Get-Date).AddMinutes(1)
$action = New-ScheduledTaskAction `
    -Execute $pwsh `
    -Argument "-NoLogo -NoProfile -File `"$runner`"" `
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
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

try {
    Register-ScheduledTask `
        -TaskPath $taskPath `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Always-on strict whole-hour V20 context prediction dispatcher; audit writes only.' `
        -Force | Out-Null
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    if (-not (Test-IgnoreNewPolicy $task.Settings.MultipleInstances)) { throw 'Task overlap policy is not IgnoreNew' }
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
    schema = 'ops.si-v20.strict-hourly-task-registration.v1'
    task_path = $taskPath
    task_name = $taskName
    state = $task.State.ToString()
    next_run_time = $taskInfo.NextRunTime.ToString('o')
    dispatcher_interval = 'PT1M'
    multiple_instances = $task.Settings.MultipleInstances.ToString()
    principal = $task.Principal.UserId
    backup_xml = if ($existingXml) { $backupXml } else { $null }
    strict_slot_table = 'bf_assistant.si_v20_strict_hourly_slot'
    audit_table = 'bf_assistant.si_v20_prediction_audit'
    operator_configurable = $false
    writes_prediction_audit_only = $true
} | ConvertTo-Json -Depth 5
