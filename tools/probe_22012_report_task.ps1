$task = Get-ScheduledTask -TaskName 'IMESBF2OperationLogReport5m' -ErrorAction SilentlyContinue
if ($null -eq $task) {
  Write-Output 'task_missing=true'
  exit 2
}
$info = Get-ScheduledTaskInfo -TaskName 'IMESBF2OperationLogReport5m'
Write-Output ("task_name=" + $task.TaskName)
Write-Output ("state=" + $task.State)
Write-Output ("last_run=" + $info.LastRunTime)
Write-Output ("last_result=" + $info.LastTaskResult)
Write-Output ("next_run=" + $info.NextRunTime)
Write-Output ("missed_runs=" + $info.NumberOfMissedRuns)
