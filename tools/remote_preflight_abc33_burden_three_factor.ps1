$ErrorActionPreference='Stop'
$Root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Names=@('abc_burden_rate.py','abc_feature_builder.py','abc_rule_catalog.py','abc_factor_audit.py','abc_term_semantics.py')
$Hashes=[ordered]@{}
foreach($Name in $Names){$Path=Join-Path $Root "自动诊断服务\$Name";$Hashes[$Name]=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash}
$Ports=[ordered]@{};foreach($Port in @(8093,8094,8768,8770,5432,11434)){$Row=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1;$Ports[[string]$Port]=if($Row){[int]$Row.OwningProcess}else{$null}}
[pscustomobject]@{ok=$true;hashes=$Hashes;ports=$Ports;service8093=(Get-Service BFV4PreviewProxy8093).Status.ToString();service8768=(Get-Service BFV4PreviewWs8768).Status.ToString()}|ConvertTo-Json -Depth 5
