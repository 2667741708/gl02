$ErrorActionPreference = 'Stop'
$taskName = 'BlastFurnace8093DailyBaseline20d'
$before = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
$beforeRun = $before.LastRunTime
Start-ScheduledTask -TaskName $taskName -TaskPath '\'
$deadline = (Get-Date).AddSeconds(180)
do {
    Start-Sleep -Seconds 5
    $info = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    if ($info.LastRunTime -gt $beforeRun -and $info.LastTaskResult -notin @(267009,267011)) {
        break
    }
} while ((Get-Date) -lt $deadline)
$final = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
[pscustomobject]@{
    task = $taskName
    last_run_time = $final.LastRunTime
    last_task_result = $final.LastTaskResult
    next_run_time = $final.NextRunTime
    started_after_previous = $final.LastRunTime -gt $beforeRun
    ok = ($final.LastRunTime -gt $beforeRun -and $final.LastTaskResult -eq 0)
} | ConvertTo-Json -Compress
if (-not ($final.LastRunTime -gt $beforeRun -and $final.LastTaskResult -eq 0)) { exit 1 }
