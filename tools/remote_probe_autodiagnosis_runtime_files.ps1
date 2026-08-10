$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V3\auto_diagnosis_service'
Write-Output ('root_exists='+(Test-Path -LiteralPath $root))
foreach($name in 'diagnosis_scheduler.py','abc_feature_builder.py','abc_rule_catalog.py','abc_rule_engine.py','store.py','local_pg_ws_bridge.py','config\abc_furnace_rules.v1.json','run_auto_diagnosis_once.ps1'){
  $path=Join-Path $root $name
  if(Test-Path -LiteralPath $path){
    $item=Get-Item -LiteralPath $path
    Write-Output ($name+'|exists|length='+$item.Length+'|sha256='+(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash)
  }else{
    Write-Output ($name+'|missing')
  }
}
$logDir=Join-Path $root 'logs'
if(Test-Path -LiteralPath $logDir){
  $latest=Get-ChildItem -LiteralPath $logDir -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if($latest){
    Write-Output ('latest_log='+$latest.FullName)
    Get-Content -LiteralPath $latest.FullName -Tail 40 -Encoding UTF8
  }
}
