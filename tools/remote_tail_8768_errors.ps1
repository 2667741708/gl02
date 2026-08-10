$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$logs='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs'
foreach($name in 'ws_8768.err.log','ws_8768.out.log'){
  $path=Join-Path $logs $name
  Write-Output ('===='+$name+'====')
  if(Test-Path -LiteralPath $path){Get-Content -LiteralPath $path -Tail 80 -Encoding UTF8}else{Write-Output 'missing'}
}
