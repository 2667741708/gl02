$ErrorActionPreference = 'Stop'
$path = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFBaselineProxy8096.json'
$raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
[ordered]@{ path = $path; raw = $raw } | ConvertTo-Json -Depth 4
