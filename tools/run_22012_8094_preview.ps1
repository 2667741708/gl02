[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Continue"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This 8094 preview runner requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = "$root\高炉前端数据"
$script = "$frontend\智能助手\backend\ollama_proxy_server.py"
$log = "$root\logs\preview_proxy_8094.log"
$authConfigPath = "$root\tools\service_configs\22012_BFV4PreviewProxy8093.json"

if (Test-Path -LiteralPath $authConfigPath -PathType Leaf) {
    $authConfig = Get-Content -LiteralPath $authConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $authConfig.env.PSObject.Properties) {
        if ($property.Name -like 'BF_LOGIN*' -and $null -ne $property.Value) {
            Set-Item -Path ("Env:" + $property.Name) -Value ([string]$property.Value)
        }
    }
}

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

# REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806 BEGIN
$env:BF_DIAGNOSIS_REVIEW_ENABLED = "1"
$env:BF_DIAGNOSIS_REVIEW_TEST_MODE = "0"
$env:BF_DIAG_REVIEW_REQUIRE_LOGIN = "0"
$env:BF_DIAG_REVIEW_ANONYMOUS_USERNAME = "onsite_8094"
$env:BF_DIAG_REVIEW_ANONYMOUS_ROLE = "现场高炉长"
$env:BF_DIAG_REVIEW_PGHOST = "127.0.0.1"
$env:BF_DIAG_REVIEW_PGPORT = "5432"
$env:BF_DIAG_REVIEW_PGDATABASE = "bf_trend"
$env:BF_DIAG_REVIEW_PGUSER = "gl02_sync"
$env:BF_DIAG_REVIEW_PGPASSWORD_ENV = "GL02_PGPASSWORD"
$env:BF_DIAG_REVIEW_PGSCHEMA = "bf_assistant"
$env:BF_DIAGNOSIS_MODEL_REVIEW_ENABLED = "1"
$env:BF_DIAGNOSIS_AI_ANALYSIS_ENABLED = "1"
$env:BF_DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED = "1"
$env:BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES = "5"
$env:BF_DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS = "30"
$env:BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS = "120"
$env:BF_DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT = "12"
# REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806 END

$python = "C:\Program Files\Python311\python.exe"
if ($ValidateOnly) {
    foreach ($required in @($python, $script, $frontend)) {
        if (-not (Test-Path -LiteralPath $required)) { throw "8094 runtime dependency is unavailable: $required" }
    }
    [ordered]@{
        schema = 'ops.8094-preview-runner.validate-only.v1'
        ok = $true
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        python = $python
        proxy = $script
    } | ConvertTo-Json -Depth 4
    exit 0
}

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting V4 proxy 8094 preview"
    Set-Location -LiteralPath $frontend
    & $python -X utf8 -u $script >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt preview proxy exited, restart in 5s"
    Start-Sleep -Seconds 5
}
