$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$candidates=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'baseline_maintainer.py' -File -ErrorAction SilentlyContinue
$target=$candidates|Where-Object{
  $_.FullName-match'V4_8093_PREVIEW' -and
  $_.FullName-notmatch'\\backups\\|\\.deploy_staging\\' -and
  (Test-Path -LiteralPath (Join-Path $_.DirectoryName 'config.yaml'))
}|Select-Object -First 1
if(-not$target){throw 'Formal V4 baseline maintainer not found'}
$service=$target.DirectoryName
$root=Split-Path -Parent $service
$tools=Join-Path $root 'tools'
$staging='C:\Users\Administrator\AppData\Local\Temp\abc33_baseline_repair'
$names=@('baseline_maintainer.py','verify_abc33_baseline_coverage.py','run_v4_daily_baseline.ps1','run_abc33_baseline_rebuild.ps1')
foreach($name in $names){if(-not(Test-Path -LiteralPath (Join-Path $staging $name))){throw "Missing staged file: $name"}}
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root ('backups\abc33_baseline_repair\'+$stamp)
New-Item -ItemType Directory -Path $backup -Force|Out-Null
$destinations=@{
  'baseline_maintainer.py'=$target.FullName
  'verify_abc33_baseline_coverage.py'=(Join-Path $tools 'verify_abc33_baseline_coverage.py')
  'run_v4_daily_baseline.ps1'=(Join-Path $tools 'run_v4_daily_baseline.ps1')
  'run_abc33_baseline_rebuild.ps1'=(Join-Path $tools 'run_abc33_baseline_rebuild.ps1')
}
foreach($name in $names){$destination=$destinations[$name];if(Test-Path -LiteralPath $destination){Copy-Item -LiteralPath $destination -Destination (Join-Path $backup $name) -Force}}
$python='C:\Program Files\Python311\python.exe'
$day=(Get-Date).Date.ToString('yyyy-MM-dd')
try{
  foreach($name in $names){Copy-Item -LiteralPath (Join-Path $staging $name) -Destination $destinations[$name] -Force}
  &$python -m py_compile $destinations['baseline_maintainer.py'] $destinations['verify_abc33_baseline_coverage.py']
  if($LASTEXITCODE-ne0){throw 'Remote baseline Python syntax check failed'}
  &powershell.exe -NoProfile -ExecutionPolicy Bypass -File $destinations['run_abc33_baseline_rebuild.ps1'] -BackfillDays 1 -EndDay $day
  if($LASTEXITCODE-ne0){throw 'Remote ABC33 baseline rebuild failed'}
  $task=Get-ScheduledTask -TaskName 'BlastFurnace8093DailyBaseline20d' -ErrorAction Stop
  $hashes=@{}
  foreach($name in $names){$hashes[$name]=(Get-FileHash -LiteralPath $destinations[$name] -Algorithm SHA256).Hash}
  [pscustomobject]@{ok=$true;backup=$backup;hashes=$hashes;task=($task.TaskPath+$task.TaskName);task_state=$task.State.ToString();task_arguments=$task.Actions.Arguments}|ConvertTo-Json -Depth 5
}catch{
  foreach($name in $names){$saved=Join-Path $backup $name;if(Test-Path -LiteralPath $saved){Copy-Item -LiteralPath $saved -Destination $destinations[$name] -Force}}
  throw
}
