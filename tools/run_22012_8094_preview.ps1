$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = "$root\高炉前端数据"
$script = "$frontend\智能助手\backend\ollama_proxy_server.py"
$log = "$root\logs\preview_proxy_8094.log"

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:BF_PROXY_HOST = "0.0.0.0"
$env:BF_PROXY_PORT = "8094"
$env:BF_INDEX_FILE = "frontend_dashboard_v3.8094_preview.server.html"
$env:BF_FRONTEND_DIR = $frontend
$env:BF_AUTOMATION_MONITOR = "1"
$env:BF_MCP_DATA_SOURCE = "storage"
$env:OLLAMA_BASE_URL = "http://10.30.220.12:11434"
$env:BF_ALLOWED_LOADED_MODELS = "chiqiong-blast-furnace:latest,chiqiong-blast-furnace:latest_s"
$env:BF_QA_KNOWLEDGE_SEARCH_MODE = "keyword"
$env:BF_PUBLIC_MODEL_NAME = "炽穹·高炉炼铁大模型"
$env:BF_QA_DB = "$frontend\data\bf_qa.sqlite3"

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting V4 proxy 8094 preview"
    Set-Location -LiteralPath $frontend
    & "C:\Program Files\Python311\python.exe" -X utf8 -u $script >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt preview proxy exited, restart in 5s"
    Start-Sleep -Seconds 5
}
