$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceDir = Join-Path $root '自动诊断服务'
$items = @(
  'baseline_maintainer.py','store.py','abc_feature_builder.py','abc_rule_catalog.py',
  'abc_rule_engine.py','diagnosis_scheduler.py','local_pg_ws_bridge.py'
)
$result = [ordered]@{}
$result.service = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
$result.p8768 = (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
$result.p8093 = (Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
$result.p8094 = (Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
$hashes = [ordered]@{}
foreach ($item in $items) {
  $hashes[$item] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $serviceDir $item)).Hash
}
$hashes['abc_furnace_rules.v1.json'] = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $serviceDir 'config\abc_furnace_rules.v1.json')).Hash
$result.hashes = $hashes
$result.http8093 = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri 'http://127.0.0.1:8093/?cb=a9verify').StatusCode
$result.http8094 = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri 'http://127.0.0.1:8094/?cb=a9verify').StatusCode
$result | ConvertTo-Json -Depth 5
