$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$task=Get-ScheduledTask -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce'
$info=Get-ScheduledTaskInfo -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce'
Write-Output ('state='+$task.State)
Write-Output ('last_result='+$info.LastTaskResult)
Write-Output ('last_run='+$info.LastRunTime.ToString('o'))
Write-Output ('next_run='+$info.NextRunTime.ToString('o'))
foreach($action in $task.Actions){
  Write-Output ('execute='+$action.Execute)
  Write-Output ('arguments='+$action.Arguments)
  Write-Output ('working_directory='+$action.WorkingDirectory)
}
