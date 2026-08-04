$configPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Config not found: $configPath"
}

$raw = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
$json = $raw | ConvertFrom-Json

$redacted = $raw | ConvertFrom-Json
foreach ($prop in @($redacted.PSObject.Properties)) {
  if ($prop.Name -match "PASSWORD|TOKEN|SECRET|KEY") {
    $redacted.($prop.Name) = "<redacted>"
  }
}
if ($redacted.env) {
  foreach ($prop in @($redacted.env.PSObject.Properties)) {
    if ($prop.Name -match "PASSWORD|TOKEN|SECRET|KEY") {
      $redacted.env.($prop.Name) = "<redacted>"
    }
  }
}

[pscustomobject]@{
  ConfigPath = $configPath
  FullConfig = $redacted
} | ConvertTo-Json -Depth 8
