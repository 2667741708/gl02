$ErrorActionPreference='Stop'
$Root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python='C:\Program Files\Python311\python.exe'
$Probe=Join-Path $Root 'tools\probe_abc33_ws_bundle.py'
$Text=(&$Python -X utf8 $Probe --url 'ws://127.0.0.1:8768' --timeout 120 2>&1)-join"`n"
if($LASTEXITCODE-ne0){throw "WS probe failed: $Text"}
$Ws=$Text|ConvertFrom-Json
if([int]$Ws.rule_count-ne33){throw "Expected 33 rules, got $($Ws.rule_count)"}
$Files=@('abc_burden_rate.py','abc_feature_builder.py','abc_rule_catalog.py','abc_factor_audit.py','abc_term_semantics.py')
$Hashes=[ordered]@{};foreach($Name in $Files){$Path=Join-Path $Root "自动诊断服务\$Name";$Hashes[$Name]=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash}
$Ports=[ordered]@{};foreach($Port in @(8093,8094,8768,8770,5432,11434)){$Row=Get-NetTCPConnection -LocalPort $Port -State Listen|Select-Object -First 1;$Ports[[string]$Port]=[int]$Row.OwningProcess}
[pscustomobject]@{ok=$true;service8768=(Get-Service BFV4PreviewWs8768).Status.ToString();ports=$Ports;hashes=$Hashes;websocket=$Ws;http8093=(Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest' -TimeoutSec 30).StatusCode}|ConvertTo-Json -Depth 9
