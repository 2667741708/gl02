$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$TaskPath = "\GL02AutoDiagnosis\"
$TaskName = "RunOnce"

"TASK_TRIGGER_START`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
try {
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
    "TASK_STARTED`t$TaskPath$TaskName"
} catch {
    "TASK_START_FAILED`t$($_.Exception.Message)"
    exit 2
}

for ($i = 1; $i -le 180; $i++) {
    Start-Sleep -Seconds 2
    $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    "TASK_POLL`t$i`tstate=$($task.State)`tlast=$($info.LastTaskResult)`tlast_run=$($info.LastRunTime)"
    if ($task.State -ne "Running") {
        break
    }
}

$finalTask = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
$finalInfo = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
"TASK_FINAL`tstate=$($finalTask.State)`tlast=$($finalInfo.LastTaskResult)`tlast_run=$($finalInfo.LastRunTime)`tnext=$($finalInfo.NextRunTime)"
"TASK_TRIGGER_END`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
if ($finalInfo.LastTaskResult -eq 0) { exit 0 }
exit 1
