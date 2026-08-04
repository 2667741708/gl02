$ErrorActionPreference = "Stop"

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$backend = Join-Path $root "高炉前端数据\智能助手\backend"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$files = @(
  "assistant_pg.py",
  "bf_knowledge_rag.py",
  "ollama_proxy_server.py"
)

$backups = foreach ($name in $files) {
  $source = Join-Path $backend $name
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Backend file not found: $source"
  }
  $destination = "$source.bak_latency_quality_safe_$stamp"
  Copy-Item -LiteralPath $source -Destination $destination -Force
  [pscustomobject]@{
    Source = $source
    Backup = $destination
  }
}

$backups | ConvertTo-Json -Depth 4
