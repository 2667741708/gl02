$ErrorActionPreference='Stop'
$baselineFile=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'run_v4_daily_baseline.ps1' -File -ErrorAction SilentlyContinue|Where-Object{$_.FullName-match'V4_8093_PREVIEW'-and$_.FullName-notmatch'\\backups\\'}|Select-Object -First 1
if(-not $baselineFile){throw 'run_v4_daily_baseline.ps1 not found'}
& $baselineFile.FullName
if($LASTEXITCODE-ne0){throw ('One-time baseline rebuild failed with exit code '+$LASTEXITCODE)}
$root=Split-Path -Parent $baselineFile.DirectoryName
$statusPath=Join-Path $root 'logs\cooling_daily_backfill_20260809.status.json'
if(Test-Path -LiteralPath $statusPath){
  $state=Get-Content -LiteralPath $statusPath -Encoding UTF8 -Raw|ConvertFrom-Json
  $state.baseline_complete=$true
  $state.baseline_completed_at=Get-Date
  $state.error=$null
  $state.updated_at=Get-Date
  $state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $statusPath -Encoding UTF8
}
$task=Get-ScheduledTask -TaskName 'BlastFurnace8093DailyBaseline20d' -ErrorAction Stop
$info=Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath
[pscustomobject]@{baseline_ok=$true;baseline_script=$baselineFile.FullName;daily_task=($task.TaskPath+$task.TaskName);task_state=$task.State.ToString();last_run=$info.LastRunTime;next_run=$info.NextRunTime;arguments=$task.Actions.Arguments}|ConvertTo-Json -Depth 4
