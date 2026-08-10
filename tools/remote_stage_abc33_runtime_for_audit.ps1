$ErrorActionPreference='Stop'
$output='C:\Users\Administrator\AppData\Local\Temp\abc33_runtime_snapshot'
if(Test-Path -LiteralPath $output){Remove-Item -LiteralPath $output -Recurse -Force}
New-Item -ItemType Directory -Path $output|Out-Null
$configs=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'abc_furnace_rules.v1.json' -File -ErrorAction SilentlyContinue
$config=$configs|Where-Object{
  $_.FullName-match'V4_8093_PREVIEW' -and
  $_.FullName-notmatch'\\backups\\|\\.deploy_staging\\'
}|Select-Object -First 1
if(-not$config){throw 'Formal V4 ABC config not found'}
$service=Split-Path -Parent $config.DirectoryName
foreach($name in @('abc_feature_builder.py','abc_rule_catalog.py','abc_rule_engine.py')){
  $source=Join-Path $service $name
  if(-not(Test-Path -LiteralPath $source)){throw "Missing runtime file: $name"}
  Copy-Item -LiteralPath $source -Destination (Join-Path $output $name) -Force
}
Copy-Item -LiteralPath $config.FullName -Destination (Join-Path $output 'abc_furnace_rules.v1.json') -Force
$files=Get-ChildItem -LiteralPath $output -File|ForEach-Object{
  [pscustomobject]@{name=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
}
[pscustomobject]@{ok=$true;service=$service;files=$files}|ConvertTo-Json -Depth 4
