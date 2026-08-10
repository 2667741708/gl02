$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service=Get-Service -Name 'BFV4PreviewWs8768'
Write-Output ("service="+$service.Status)
foreach($port in 8093,8094,8768,8770,11434){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($item){Write-Output ("port_$port="+$item.OwningProcess)}else{Write-Output ("port_$port=NONE")}
}
foreach($relative in '自动诊断服务\abc_feature_builder.py','自动诊断服务\abc_rule_catalog.py','自动诊断服务\abc_rule_engine.py','自动诊断服务\local_pg_ws_bridge.py','自动诊断服务\config\abc_furnace_rules.v1.json'){
  $hash=(Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash
  Write-Output ($relative+'='+$hash)
}
