$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据'
$result=[ordered]@{}
foreach($port in 8093,8094){
  $response=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/?cb=probe" -TimeoutSec 30
  $result["port$port"]=[ordered]@{
    status=[int]$response.StatusCode
    length=$response.Content.Length
    abc_asset=$response.Content.Contains('abc-furnace-rules-production.js')
    score_preview_version=$response.Content.Contains('abc33-20260810-score-preview-r1')
  }
}
$matches=@()
Get-ChildItem -LiteralPath $root -Filter '*.html' | ForEach-Object {
  $content=Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8
  if($content.Contains('abc-furnace-rules-production.js') -or $content.Contains('33项炉况')){
    $matches+=[ordered]@{path=$_.FullName;abc_asset=$content.Contains('abc-furnace-rules-production.js');score_preview_version=$content.Contains('abc33-20260810-score-preview-r1')}
  }
}
$result.files=$matches
$result | ConvertTo-Json -Depth 5
