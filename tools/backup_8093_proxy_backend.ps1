$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$target = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
if (-not (Test-Path -LiteralPath $target)) {
  throw "Target backend file not found: $target"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = "$target.bak_latency_opt_$stamp"
Copy-Item -LiteralPath $target -Destination $backup -Force

[pscustomobject]@{
  target = $target
  backup = $backup
} | ConvertTo-Json -Depth 4
