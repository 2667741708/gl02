$ErrorActionPreference='Stop'
$candidates=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'baseline_maintainer.py' -File -ErrorAction SilentlyContinue
$target=$candidates|Where-Object{
  $_.FullName-match'V4_8093_PREVIEW' -and
  $_.FullName-notmatch'\\backups\\|\\.deploy_staging\\' -and
  (Test-Path -LiteralPath (Join-Path $_.DirectoryName 'config.yaml'))
}|Select-Object -First 1
if(-not$target){throw 'V4 baseline_maintainer.py not found'}
$staged='C:\Users\Administrator\AppData\Local\Temp\baseline_maintainer_expansion_hourly_daily.py'
if(-not(Test-Path -LiteralPath $staged)){throw 'Staged baseline file not found'}
$root=Split-Path -Parent $target.DirectoryName
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root ('backups\expansion_hourly_daily_baseline\'+$stamp)
New-Item -ItemType Directory -Force -Path $backup|Out-Null
$saved=Join-Path $backup 'baseline_maintainer.py'
Copy-Item -LiteralPath $target.FullName -Destination $saved -Force
try{
  Copy-Item -LiteralPath $staged -Destination $target.FullName -Force
  & 'C:\Program Files\Python311\python.exe' -m py_compile $target.FullName
  if($LASTEXITCODE-ne0){throw 'Remote py_compile failed'}
  $config=Join-Path $target.DirectoryName 'config.yaml'
  $day=(Get-Date).Date.ToString('yyyy-MM-dd')
  & 'C:\Program Files\Python311\python.exe' -X utf8 $target.FullName --build-day $day --baseline-days 30 --cooling-only --write --config $config
  if($LASTEXITCODE-ne0){throw 'Cooling baseline rebuild failed'}
  $task=Get-ScheduledTask -TaskName 'BlastFurnace8093DailyBaseline20d' -ErrorAction Stop
  [pscustomobject]@{ok=$true;backup=$backup;target_hash=(Get-FileHash -LiteralPath $target.FullName -Algorithm SHA256).Hash;task=($task.TaskPath+$task.TaskName);task_state=$task.State.ToString();task_arguments=$task.Actions.Arguments}|ConvertTo-Json -Depth 4
}catch{
  Copy-Item -LiteralPath $saved -Destination $target.FullName -Force
  throw
}
