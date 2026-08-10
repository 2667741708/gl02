$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_common_factors'
$process=Get-Process -Id 10324 -ErrorAction SilentlyContinue
Write-Output ('running='+[bool]$process)
foreach($name in 'deploy_8768.stdout.log','deploy_8768.stderr.log'){
  $path=Join-Path $stage $name
  Write-Output ('===='+$name+'====')
  if(Test-Path -LiteralPath $path){Get-Content -LiteralPath $path -Tail 80 -Encoding UTF8}else{Write-Output 'not_created'}
}
