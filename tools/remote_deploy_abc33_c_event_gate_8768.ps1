$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_c_event_gate'
$service='BFV4PreviewWs8768'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root "backups\abc33_c_event_gate_8768_$stamp"
$python='C:\Program Files\Python311\python.exe'
$files=@(
  @{Staged='abc_feature_builder.py';Relative='自动诊断服务\abc_feature_builder.py'},
  @{Staged='abc_rule_engine.py';Relative='自动诊断服务\abc_rule_engine.py'},
  @{Staged='abc_public_review.py';Relative='自动诊断服务\abc_public_review.py'}
)
function Get-PortPid([int]$port){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
  if($item){return [int]$item.OwningProcess}
  return $null
}
function Wait-Port([int]$port,[bool]$expected,[int]$seconds){
  $deadline=(Get-Date).AddSeconds($seconds)
  do{
    if(($null-ne(Get-PortPid $port))-eq$expected){return}
    Start-Sleep -Milliseconds 500
  }while((Get-Date)-lt$deadline)
  throw "port $port did not reach listening=$expected"
}
$before=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8093','p8094','p8768','p8770','p11434'){if(-not$before[$name]){throw "missing protected listener: $name"}}
foreach($entry in $files){
  $source=Join-Path $stage $entry.Staged
  if(-not(Test-Path -LiteralPath $source)){throw "missing staged file: $source"}
  & $python -m py_compile $source
  if($LASTEXITCODE-ne0){throw "syntax validation failed: $($entry.Staged)"}
}
New-Item -ItemType Directory -Path $backup -Force|Out-Null
foreach($entry in $files){
  $target=Join-Path $root $entry.Relative
  $entry.Existed=Test-Path -LiteralPath $target
  if($entry.Existed){Copy-Item -LiteralPath $target -Destination (Join-Path $backup $entry.Staged) -Force}
}
$changed=$false
try{
  Stop-Service -Name $service -Force
  Wait-Port 8768 $false 90
  foreach($entry in $files){
    $target=Join-Path $root $entry.Relative
    $next="$target.next"
    Copy-Item -LiteralPath (Join-Path $stage $entry.Staged) -Destination $next -Force
    Move-Item -LiteralPath $next -Destination $target -Force
  }
  $changed=$true
  Start-Service -Name $service
  Wait-Port 8768 $true 150
  $probePath=Join-Path $root 'tools\probe_abc33_ws_bundle.py'
  $probeText=(& $python -X utf8 $probePath --url 'ws://127.0.0.1:8768' --timeout 120 2>&1)-join "`n"
  if($LASTEXITCODE-ne0){throw "8768 probe failed: $probeText"}
  $probe=$probeText|ConvertFrom-Json
  if([int]$probe.rule_count-ne33){throw "8768 returned $($probe.rule_count) rules"}
  $needs=0
  if($probe.status_counts.needs_data){$needs=[int]$probe.status_counts.needs_data}
  if($needs-ne0){throw "8768 returned $needs needs_data rules"}
  $after=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
  foreach($name in 'p8093','p8094','p8770','p11434'){if($after[$name]-ne$before[$name]){throw "protected PID changed: $name"}}
}catch{
  if($changed){
    Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
    Wait-Port 8768 $false 90
    foreach($entry in $files){
      $target=Join-Path $root $entry.Relative
      if($entry.Existed){Copy-Item -LiteralPath (Join-Path $backup $entry.Staged) -Destination $target -Force}
      elseif(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target -Force}
    }
  }
  if((Get-Service -Name $service).Status-ne'Running'){
    Start-Service -Name $service -ErrorAction SilentlyContinue
    Wait-Port 8768 $true 150
  }
  throw
}
$hashes=foreach($entry in $files){
  $target=Join-Path $root $entry.Relative
  [ordered]@{path=$entry.Relative;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash}
}
[ordered]@{ok=$true;backup=$backup;before=$before;after=$after;probe=$probe;hashes=$hashes}|ConvertTo-Json -Depth 8
