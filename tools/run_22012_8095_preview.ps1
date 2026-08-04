$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
$frontend = (Get-ChildItem -LiteralPath $root -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName "frontend_dashboard_v3.8095_preview.server.html")
} | Select-Object -First 1).FullName
$script = (Get-ChildItem -LiteralPath $frontend -Recurse -Filter "ollama_proxy_server_8095.py" | Select-Object -First 1).FullName
$log = "$root\logs\preview_proxy_8095.log"

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:BF_PROXY_HOST = "0.0.0.0"
$env:BF_PROXY_PORT = "8095"
$env:BF_INDEX_FILE = "frontend_dashboard_v3.8095_preview.server.html"
$env:BF_FRONTEND_DIR = $frontend
$env:BF_AUTOMATION_MONITOR = "1"
$env:BF_MCP_DATA_SOURCE = "storage"
$env:OLLAMA_BASE_URL = "http://10.30.220.12:11434"
$env:BF_QA_KNOWLEDGE_SEARCH_MODE = "keyword"
$env:BF_PUBLIC_MODEL_NAME = "Blast Furnace LLM"
$env:BF_QA_DB = (Join-Path $frontend "data\bf_qa.sqlite3")
$env:BF_LLM_MODEL = ""

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting V4 proxy 8095 preview"
    Set-Location -LiteralPath $frontend
    & "C:\Program Files\Python311\python.exe" -X utf8 -u $script >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt preview proxy exited, restart in 5s"
    Start-Sleep -Seconds 5
}
