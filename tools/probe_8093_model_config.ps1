$configPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFV4PreviewProxy8093.json"
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

$envPairs = @{}
foreach ($prop in $json.env.PSObject.Properties) {
  if ($prop.Name -match "PASSWORD|TOKEN|SECRET|KEY") {
    $envPairs[$prop.Name] = "<redacted>"
  } else {
    $envPairs[$prop.Name] = $prop.Value
  }
}

[pscustomobject]@{
  ConfigPath = $configPath
  Name = $json.name
  ServiceName = $json.service_name
  Command = $json.command
  FullConfig = $redacted
  Workdir = $json.workdir
  Env = $envPairs
} | ConvertTo-Json -Depth 6
