$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$python='C:\Program Files\Python311\python.exe'
function Get-PortPid([int]$port){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if($item){return [int]$item.OwningProcess}
  return $null
}
$service=Get-Service -Name 'BFV4PreviewWs8768'
$ports=[ordered]@{}
foreach($port in 8093,8094,8768,8770,11434){$ports["p$port"]=Get-PortPid $port}
$probeText=(& $python -X utf8 (Join-Path $root 'tools\probe_abc33_ws_bundle.py') --url 'ws://127.0.0.1:8768' --timeout 120 2>&1)-join "`n"
if($LASTEXITCODE-ne0){throw "WebSocket probe failed: $probeText"}
$probe=$probeText|ConvertFrom-Json
$http=[ordered]@{}
foreach($port in 8093,8094){
  $response=Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/furnace-rules/latest" -TimeoutSec 30 -UseBasicParsing
  $body=$response.Content|ConvertFrom-Json
  $http["p$port"]=[ordered]@{status=[int]$response.StatusCode;rule_count=[int]$body.rules.Count;schema=$body.schema_version}
}
$files=@(
  '自动诊断服务\abc_factor_audit.py',
  '自动诊断服务\abc_feature_builder.py',
  '自动诊断服务\abc_rule_engine.py',
  '自动诊断服务\abc_rule_catalog.py',
  '自动诊断服务\config\abc_furnace_rules.v1.json'
)
$hashes=[ordered]@{}
foreach($relative in $files){$hashes[$relative]=(Get-FileHash -LiteralPath (Join-Path $root $relative) -Algorithm SHA256).Hash}
$result=[ordered]@{
  checked_at=(Get-Date).ToString('o')
  service=[ordered]@{name=$service.Name;status=$service.Status.ToString()}
  ports=$ports
  websocket=$probe
  http=$http
  hashes=$hashes
}|ConvertTo-Json -Depth 8
$output='C:\Users\Administrator\AppData\Local\Temp\abc33_runtime_acceptance.json'
$result|Set-Content -LiteralPath $output -Encoding UTF8
$result
