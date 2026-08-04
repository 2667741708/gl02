$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = Join-Path $root 'logs\furnace_conditions_stage_20260715'
$target = Join-Path $root '高炉前端数据\assets\furnace-conditions'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\furnace_conditions_$stamp"
$names = @('normal.png','lowline.png','edge.png','center.png','channel.png','cold.png','hot.png','column.png')

foreach ($name in $names) {
  $path = Join-Path $stage $name
  if (-not (Test-Path -LiteralPath $path)) { throw "Staged furnace asset missing: $path" }
  if ((Get-Item -LiteralPath $path).Length -lt 100000) { throw "Staged furnace asset is unexpectedly small: $path" }
}

if (Test-Path -LiteralPath $target) {
  New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
  Copy-Item -LiteralPath $target -Destination $backup -Recurse -Force
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($name in $names) {
  Copy-Item -LiteralPath (Join-Path $stage $name) -Destination (Join-Path $target $name) -Force
}

$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8093/assets/furnace-conditions/cold.png' -UseBasicParsing -TimeoutSec 45
if ([int]$response.StatusCode -ne 200 -or $response.RawContentLength -lt 100000) {
  throw 'Remote furnace asset HTTP verification failed.'
}
[pscustomobject]@{
  Backup = $backup
  Target = $target
  AssetCount = ($names | Where-Object { Test-Path -LiteralPath (Join-Path $target $_) }).Count
  ColdHttpStatus = [int]$response.StatusCode
  ColdHttpLength = $response.RawContentLength
} | ConvertTo-Json -Depth 3
