$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$target=Join-Path $root '自动诊断服务\diagnosis_scheduler.py'
$staged='C:\Users\Administrator\AppData\Local\Temp\abc33_common_factors\diagnosis_scheduler.py'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root ("backups\abc33_scheduler_$stamp\diagnosis_scheduler.py")
$taskPath='\GL02AutoDiagnosis\'
$taskName='RunOnce'
$python='C:\Program Files\Python311\python.exe'
function Get-PortPid([int]$port){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($item){return [int]$item.OwningProcess}
  return $null
}
$before=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8093','p8094','p8768','p8770','p11434'){if(-not $before[$name]){throw "missing listener: $name"}}
if(-not(Test-Path -LiteralPath $staged)){throw 'staged scheduler is unavailable'}
if(-not(Test-Path -LiteralPath $target)){throw 'target scheduler is unavailable'}
& $python -m py_compile $staged
if($LASTEXITCODE -ne 0){throw 'scheduler syntax validation failed'}
New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
Copy-Item -LiteralPath $target -Destination $backup -Force
$deployed=$false
try{
  Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
  $next="$target.next"
  Copy-Item -LiteralPath $staged -Destination $next -Force
  Move-Item -LiteralPath $next -Destination $target -Force
  $deployed=$true
  if((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash){throw 'scheduler hash mismatch'}
  Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
}catch{
  if($deployed){Copy-Item -LiteralPath $backup -Destination $target -Force}
  Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
  throw
}
$after=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8093','p8094','p8768','p8770','p11434'){if($after[$name] -ne $before[$name]){throw "protected PID changed: $name"}}
[ordered]@{ok=$true;backup=$backup;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash;before=$before;after=$after}|ConvertTo-Json -Depth 5
