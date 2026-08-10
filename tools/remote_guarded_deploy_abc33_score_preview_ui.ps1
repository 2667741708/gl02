$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)

$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_score_preview_ui'
$service8093='BFV4PreviewProxy8093'
$asset=Join-Path $root '高炉前端数据\assets\abc-furnace-rules-production.js'
$page8093=Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$page8094=Join-Path $root '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html'
$stagedAsset=Join-Path $stage 'abc-furnace-rules-production.js'
$version='abc33-20260810-score-preview-r1'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root "backups\abc33_score_preview_ui_$stamp"

function Get-PortPid([int]$port){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
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
  if($content.Contains('abc-furnace-rules-production.js')){
    $updated=[regex]::Replace($content,'abc-furnace-rules-production\.js(?:\?v=[^"''<\s]+)?',"abc-furnace-rules-production.js?v=$version")
  }else{
    $tag="<script src=`"assets/abc-furnace-rules-production.js?v=$version`"></script>"
    if(-not$content.Contains('</body>')){throw "body closing tag missing: $path"}
    $updated=$content.Replace('</body>',"$tag`r`n</body>")
  }
  if(-not$updated.Contains("?v=$version")){throw "ABC33 version replacement failed: $path"}
  $next="$path.next"
  Set-Content -LiteralPath $next -Value $updated -Encoding UTF8 -NoNewline
  Move-Item -LiteralPath $next -Destination $path -Force
}

$before=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8093','p8094','p8768','p8770','p11434'){if(-not$before[$name]){throw "missing listener: $name"}}
foreach($path in $asset,$page8093,$page8094,$stagedAsset){if(-not(Test-Path -LiteralPath $path)){throw "missing file: $path"}}
$stagedContent=Get-Content -LiteralPath $stagedAsset -Raw -Encoding UTF8
if(-not$stagedContent.Contains('zeroCount')){throw 'staged asset is missing valid-zero logic'}
if(-not$stagedContent.Contains("release_state==='score_preview'")){throw 'staged asset is missing score-preview logic'}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $asset -Destination (Join-Path $backup 'abc-furnace-rules-production.js') -Force
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup 'frontend_dashboard_v3.server.html') -Force
Copy-Item -LiteralPath $page8094 -Destination (Join-Path $backup 'frontend_dashboard_v3.8094_preview.server.html') -Force
$changed=$false
try{
  Stop-Service -Name $service8093 -Force
  Wait-Port 8093 $false 60
  $next="$asset.next"
  Copy-Item -LiteralPath $stagedAsset -Destination $next -Force
  Move-Item -LiteralPath $next -Destination $asset -Force
  $changed=$true
  Update-PageVersion $page8093
  Update-PageVersion $page8094
}catch{
  if($changed){
    Copy-Item -LiteralPath (Join-Path $backup 'abc-furnace-rules-production.js') -Destination $asset -Force
    Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.server.html') -Destination $page8093 -Force
    Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.8094_preview.server.html') -Destination $page8094 -Force
  }
  throw
}finally{
  Start-Service -Name $service8093 -ErrorAction SilentlyContinue
  Wait-Port 8093 $true 90
}

$after=@{p8093=Get-PortPid 8093;p8094=Get-PortPid 8094;p8768=Get-PortPid 8768;p8770=Get-PortPid 8770;p11434=Get-PortPid 11434}
foreach($name in 'p8094','p8768','p8770','p11434'){if($after[$name]-ne$before[$name]){throw "protected PID changed: $name"}}
$http8093=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$stamp#optimization" -TimeoutSec 30
$http8094=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?cb=$stamp#optimization" -TimeoutSec 30
$asset8093=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 30
$asset8094=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 30
foreach($response in $http8093,$http8094){if($response.StatusCode-ne200-or-not$response.Content.Contains("?v=$version")){throw 'page verification failed'}}
foreach($response in $asset8093,$asset8094){if($response.StatusCode-ne200-or-not$response.Content.Contains('zeroCount')-or-not$response.Content.Contains("release_state==='score_preview'")){throw 'asset verification failed'}}

[ordered]@{
  ok=$true
  backup=$backup
  guard_paused=$true
  guard_restored=((Get-Service -Name $service8093).Status-eq'Running')
  before=$before
  after=$after
  page_version=$version
  asset_sha256=(Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
  http8093=[int]$http8093.StatusCode
  http8094=[int]$http8094.StatusCode
}|ConvertTo-Json -Depth 5
