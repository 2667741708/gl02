$ErrorActionPreference = "Stop"

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$backend = Join-Path $root "高炉前端数据\智能助手\backend"
$python = "C:\Program Files\Python311\python.exe"
$files = @(
  (Join-Path $backend "assistant_pg.py"),
  (Join-Path $backend "bf_knowledge_rag.py"),
  (Join-Path $backend "ollama_proxy_server.py")
)

& $python -m py_compile @files
if ($LASTEXITCODE -ne 0) {
  throw "Remote backend py_compile failed with exit code $LASTEXITCODE"
}

[pscustomobject]@{
  Python = $python
  Files = $files
  PyCompile = $true
} | ConvertTo-Json -Depth 4
