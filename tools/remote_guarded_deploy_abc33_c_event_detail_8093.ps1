$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_c_event_detail'
$service8093='BFV4PreviewProxy8093'
$asset=Join-Path $root '高炉前端数据\assets\abc-furnace-rules-production.js'
$proxy=Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$page8093=Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$page8094=Join-Path $root '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html'
$stagedAsset=Join-Path $stage 'abc-furnace-rules-production.js'
$stagedProxy=Join-Path $stage 'ollama_proxy_server.py'
$version='abc33-20260810-c-event-detail-r3'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root "backups\abc33_c_event_detail_$stamp"
$python='C:\Program Files\Python311\python.exe'
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
function Update-PageVersion([string]$path){
  $content=Get-Content -LiteralPath $path -Raw -Encoding UTF8
  $updated=[regex]::Replace($content,'abc-furnace-rules-production\.js(?:\?v=[^"''<\s]+)?',"abc-furnace-rules-production.js?v=$version")
  if(-not$updated.Contains("?v=$version")){throw "ABC33 version replacement failed: $path"}
  Set-Content -LiteralPath "$path.next" -Value $updated -Encoding UTF8 -NoNewline
  Move-Item -LiteralPath "$path.next" -Destination $path -Force
}
$before=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8093','p8094','p8768','p8770','p11434'){if(-not$before[$name]){throw "missing protected listener: $name"}}
foreach($path in $asset,$proxy,$page8093,$page8094,$stagedAsset,$stagedProxy){if(-not(Test-Path -LiteralPath $path)){throw "missing file: $path"}}
& $python -m py_compile $stagedProxy
if($LASTEXITCODE-ne0){throw 'proxy syntax validation failed'}
$stagedContent=Get-Content -LiteralPath $stagedAsset -Raw -Encoding UTF8
foreach($marker in '全部炉壳温度点位','严重事件交叉确认','metricRows','furnace_rule_detail.v2'){
  if($marker-eq'furnace_rule_detail.v2'){continue}
  if(-not$stagedContent.Contains($marker)){throw "staged asset missing marker: $marker"}
}
New-Item -ItemType Directory -Path $backup -Force|Out-Null
Copy-Item -LiteralPath $asset -Destination (Join-Path $backup 'abc-furnace-rules-production.js') -Force
Copy-Item -LiteralPath $proxy -Destination (Join-Path $backup 'ollama_proxy_server.py') -Force
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup 'frontend_dashboard_v3.server.html') -Force
Copy-Item -LiteralPath $page8094 -Destination (Join-Path $backup 'frontend_dashboard_v3.8094_preview.server.html') -Force
$changed=$false
try{
  Stop-Service -Name $service8093 -Force
  Wait-Port 8093 $false 60
  $changed=$true
  Copy-Item -LiteralPath $stagedAsset -Destination "$asset.next" -Force
  Move-Item -LiteralPath "$asset.next" -Destination $asset -Force
  Copy-Item -LiteralPath $stagedProxy -Destination "$proxy.next" -Force
  Move-Item -LiteralPath "$proxy.next" -Destination $proxy -Force
  Update-PageVersion $page8093
  Update-PageVersion $page8094
}catch{
  if($changed){
    Copy-Item -LiteralPath (Join-Path $backup 'abc-furnace-rules-production.js') -Destination $asset -Force
    Copy-Item -LiteralPath (Join-Path $backup 'ollama_proxy_server.py') -Destination $proxy -Force
    Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.server.html') -Destination $page8093 -Force
    Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.8094_preview.server.html') -Destination $page8094 -Force
  }
  throw
}finally{
  Start-Service -Name $service8093 -ErrorAction SilentlyContinue
  Wait-Port 8093 $true 120
}
$after=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8094','p8768','p8770','p11434'){if($after[$name]-ne$before[$name]){throw "protected PID changed: $name"}}
$page=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$version#optimization" -TimeoutSec 30
$assetResponse=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 30
$detail=Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/C7/detail' -TimeoutSec 60
if($page.StatusCode-ne200-or-not$page.Content.Contains("?v=$version")){throw '8093 page version verification failed'}
if($assetResponse.StatusCode-ne200-or-not$assetResponse.Content.Contains('全部炉壳温度点位')){throw '8093 asset verification failed'}
if($detail.schema_version-ne'furnace_rule_detail.v2'){throw "unexpected detail schema: $($detail.schema_version)"}
if([int]$detail.sensor_review.body_metrics.Count-ne80){throw "C7 body point count is $($detail.sensor_review.body_metrics.Count)"}
[ordered]@{
  ok=$true;backup=$backup;guard_paused=$true;guard_restored=((Get-Service -Name $service8093).Status-eq'Running')
  before=$before;after=$after;page_version=$version;http8093=[int]$page.StatusCode
  detail_schema=$detail.schema_version;detail_metric_count=[int]$detail.sensor_review.metric_count
  detail_body_count=[int]$detail.sensor_review.body_metrics.Count;detail_missing_count=[int]$detail.sensor_review.missing_count
  asset_sha256=(Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
  proxy_sha256=(Get-FileHash -LiteralPath $proxy -Algorithm SHA256).Hash
}|ConvertTo-Json -Depth 6
