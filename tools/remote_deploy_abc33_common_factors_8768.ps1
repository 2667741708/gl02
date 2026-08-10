$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_common_factors'
$service='BFV4PreviewWs8768'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root ("backups\abc33_common_factors_$stamp")
$python='C:\Program Files\Python311\python.exe'
$files=@(
  @{Staged='abc_factor_audit.py';Relative='自动诊断服务\abc_factor_audit.py'},
  @{Staged='abc_feature_builder.py';Relative='自动诊断服务\abc_feature_builder.py'},
  @{Staged='abc_rule_catalog.py';Relative='自动诊断服务\abc_rule_catalog.py'},
  @{Staged='abc_rule_engine.py';Relative='自动诊断服务\abc_rule_engine.py'},
  @{Staged='local_pg_ws_bridge.py';Relative='自动诊断服务\local_pg_ws_bridge.py'},
  @{Staged='recommendation_audit_store.py';Relative='自动诊断服务\recommendation_audit_store.py'},
  @{Staged='abc_furnace_rules.v1.json';Relative='自动诊断服务\config\abc_furnace_rules.v1.json'}
)
function Get-PortPid([int]$port){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($item){return [int]$item.OwningProcess}
  return $null
}
function Wait-Port([int]$port,[bool]$expected,[int]$seconds){
  $deadline=(Get-Date).AddSeconds($seconds)
  do{
    if(($null-ne(Get-PortPid $port))-eq$expected){return}
    Start-Sleep -Seconds 1
  }while((Get-Date)-lt$deadline)
  throw "port $port did not reach listening=$expected"
}
$before=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
if(-not $before.p8093 -or -not $before.p8094 -or -not $before.p8768 -or -not $before.p11434){throw 'protected listener precondition failed'}
foreach($entry in $files){
  $source=Join-Path $stage $entry.Staged
  $target=Join-Path $root $entry.Relative
  if(-not(Test-Path -LiteralPath $source)){throw "missing staged file: $source"}
  $entry.Existed=Test-Path -LiteralPath $target
}
foreach($name in 'abc_factor_audit.py','abc_feature_builder.py','abc_rule_catalog.py','abc_rule_engine.py','local_pg_ws_bridge.py','recommendation_audit_store.py'){
  & $python -m py_compile (Join-Path $stage $name)
  if($LASTEXITCODE-ne0){throw "syntax validation failed: $name"}
}
Get-Content -LiteralPath (Join-Path $stage 'abc_furnace_rules.v1.json') -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach($entry in $files){
  if(-not $entry.Existed){continue}
  $saved=Join-Path $backup $entry.Relative
  New-Item -ItemType Directory -Path (Split-Path -Parent $saved) -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $root $entry.Relative) -Destination $saved -Force
}
$deployed=$false
$probeResult=$null
try{
  Stop-Service -Name $service -Force
  Wait-Port 8768 $false 90
  foreach($entry in $files){
    $target=Join-Path $root $entry.Relative
    $next="$target.next"
    Copy-Item -LiteralPath (Join-Path $stage $entry.Staged) -Destination $next -Force
    Move-Item -LiteralPath $next -Destination $target -Force
  }
  $deployed=$true
  Start-Service -Name $service
  Wait-Port 8768 $true 150
  $after=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
  if($after.p8093 -ne $before.p8093 -or $after.p8094 -ne $before.p8094 -or $after.p8770 -ne $before.p8770 -or $after.p11434 -ne $before.p11434){throw 'protected PID changed'}
  $probePath=Join-Path $root 'tools\probe_abc33_ws_bundle.py'
  if(-not(Test-Path -LiteralPath $probePath)){throw "missing production probe: $probePath"}
  $probeText=(& $python -X utf8 $probePath --url 'ws://127.0.0.1:8768' --timeout 120 2>&1)-join "`n"
  if($LASTEXITCODE-ne0){throw "8768 ABC33 probe failed: $probeText"}
  $probeResult=$probeText|ConvertFrom-Json
  if([int]$probeResult.rule_count-ne33){throw "8768 returned $($probeResult.rule_count) ABC rules"}
  if([int]$probeResult.data_complete_count-ne33){throw "8768 returned only $($probeResult.data_complete_count) data-complete ABC rules"}
  $needsDataCount=0
  if($probeResult.status_counts.needs_data){$needsDataCount=[int]$probeResult.status_counts.needs_data}
  if($needsDataCount-ne0){throw "8768 returned $needsDataCount needs_data ABC rules"}
}catch{
  if($deployed){
    Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
    Wait-Port 8768 $false 90
    foreach($entry in $files){
      $target=Join-Path $root $entry.Relative
      if($entry.Existed){
        Copy-Item -LiteralPath (Join-Path $backup $entry.Relative) -Destination $target -Force
      }elseif(Test-Path -LiteralPath $target){
        Remove-Item -LiteralPath $target -Force
      }
    }
  }
  if((Get-Service -Name $service).Status -ne 'Running'){
    Start-Service -Name $service -ErrorAction SilentlyContinue
    Wait-Port 8768 $true 150
  }
  throw
}
$hashes=foreach($entry in $files){
  $target=Join-Path $root $entry.Relative
  [ordered]@{path=$target;sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash}
}
[ordered]@{ok=$true;backup=$backup;before=$before;after=$after;probe=$probeResult;hashes=$hashes}|ConvertTo-Json -Depth 8
