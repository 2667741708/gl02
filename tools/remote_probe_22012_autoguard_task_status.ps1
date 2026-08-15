[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Task = Get-ScheduledTask -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce' -ErrorAction Stop
$Info = Get-ScheduledTaskInfo -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce' -ErrorAction Stop
[ordered]@{
    ok = $true
    state_code = [int]$Task.State
    last_run_time = $Info.LastRunTime.ToString('o')
    last_task_result = [long]$Info.LastTaskResult
    next_run_time = $Info.NextRunTime.ToString('o')
} | ConvertTo-Json -Depth 3
