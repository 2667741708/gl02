$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = if ($env:BF_8093_PROJECT_ROOT) {
    $env:BF_8093_PROJECT_ROOT
} else {
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
}
$EndpointTimeoutSeconds = if ($env:BF_8093_PROBE_TIMEOUT_SECONDS) {
    [int]$env:BF_8093_PROBE_TIMEOUT_SECONDS
} else {
    5
}

function Get-EndpointResult {
    param([Parameter(Mandatory = $true)][string]$Uri)

    $started = Get-Date
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $EndpointTimeoutSeconds
        $content = $response.Content
        try {
            $content = $content | ConvertFrom-Json
        } catch {
            # Keep non-JSON endpoint content as text.
        }
        return [pscustomobject]@{
            uri = $Uri
            ok = $true
            status_code = [int]$response.StatusCode
            elapsed_ms = [int]((Get-Date) - $started).TotalMilliseconds
            content = $content
            error = $null
        }
    } catch {
        return [pscustomobject]@{
            uri = $Uri
            ok = $false
            status_code = $null
            elapsed_ms = [int]((Get-Date) - $started).TotalMilliseconds
            content = $null
            error = $_.Exception.Message
        }
    }
}

$configDirectory = Join-Path $ProjectRoot "tools\service_configs"
$proxyConfigPath = Join-Path $configDirectory "22012_BFV4PreviewProxy8093.json"
$ollamaConfigPath = Join-Path $configDirectory "22012_BFOllama11434.json"
$logDirectory = Join-Path $ProjectRoot "logs"

$proxyConfig = $null
if (Test-Path -LiteralPath $proxyConfigPath) {
    $proxyConfig = Get-Content -LiteralPath $proxyConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
$ollamaConfig = $null
if (Test-Path -LiteralPath $ollamaConfigPath) {
    $ollamaConfig = Get-Content -LiteralPath $ollamaConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

$serviceRows = foreach ($name in @("BFV4PreviewProxy8093", "BFOllama11434", "BFV4PreviewWs8768")) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    [pscustomobject]@{
        name = $name
        exists = $null -ne $service
        status = if ($service) { $service.Status.ToString() } else { $null }
        start_type = if ($service) { $service.StartType.ToString() } else { $null }
    }
}

$outLog = Join-Path $logDirectory "proxy_8093.service.out.log"
$errLog = Join-Path $logDirectory "proxy_8093.service.err.log"
$runnerLog = Join-Path $logDirectory "proxy_8093.service.runner.log"
$healthLog = Join-Path $logDirectory "proxy_8093.health.log"
$logRows = foreach ($path in @($outLog, $errLog, $runnerLog, $healthLog)) {
    $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
    [pscustomobject]@{
        path = $path
        exists = $null -ne $item
        length = if ($item) { [long]$item.Length } else { $null }
        last_write_time = if ($item) { $item.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    }
}

$result = [pscustomobject]@{
    schema = "ops.8093.assistant-health.readonly.v1"
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    project_root = $ProjectRoot
    services = @($serviceRows)
    endpoints = @(
        Get-EndpointResult -Uri "http://127.0.0.1:8093/api/ollama/status"
        Get-EndpointResult -Uri "http://127.0.0.1:11434/api/ps"
    )
    config = [pscustomobject]@{
        proxy_model = $proxyConfig.env.BF_LLM_MODEL
        proxy_ollama_base_url = $proxyConfig.env.OLLAMA_BASE_URL
        proxy_knowledge_search_mode = $proxyConfig.env.BF_QA_KNOWLEDGE_SEARCH_MODE
        proxy_mcp_data_source = $proxyConfig.env.BF_MCP_DATA_SOURCE
        ollama_max_loaded_models = $ollamaConfig.env.OLLAMA_MAX_LOADED_MODELS
        ollama_keep_alive = $ollamaConfig.env.OLLAMA_KEEP_ALIVE
        ollama_health_model = $ollamaConfig.health.httpPost.model
    }
    logs = @($logRows)
}

$result | ConvertTo-Json -Depth 8
