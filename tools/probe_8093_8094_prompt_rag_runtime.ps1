$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-8093-8094-PROMPT-RAG-RUNTIME-20260805
# Read-only probe. It reports only non-secret runtime switches and source markers.

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$backend = Join-Path $root "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$ragBackend = Join-Path $root "高炉前端数据\智能助手\backend\bf_knowledge_rag.py"
$python = "C:\Program Files\Python311\python.exe"

function Get-ProcessEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][int]$TargetProcessId,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $code = @"
import sys
import psutil

try:
    value = psutil.Process(int(sys.argv[1])).environ().get(sys.argv[2], "")
    print(value)
except Exception as exc:
    print("ENV_ERROR:" + str(exc))
"@
    $temporary = Join-Path $env:TEMP ("bf_prompt_rag_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($temporary, $code, [Text.UTF8Encoding]::new($false))
    try {
        return (& $python $temporary $TargetProcessId $Name 2>$null) -join "`n"
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Get-EffectiveBool([string]$Value, [bool]$Default) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
    return $Value.Trim().ToLowerInvariant() -notin @("0", "false", "no", "off")
}

function Get-EffectiveInt([string]$Value, [int]$Default) {
    $parsed = 0
    if ([int]::TryParse($Value, [ref]$parsed)) { return $parsed }
    return $Default
}

foreach ($required in @($backend, $ragBackend, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "required file is missing: $required"
    }
}

$source = Get-Content -LiteralPath $backend -Raw -Encoding UTF8
$ragSource = Get-Content -LiteralPath $ragBackend -Raw -Encoding UTF8
$fixedRulesAt = $source.IndexOf("{project_rules}")
$furnaceContextAt = $source.IndexOf("【炉况上下文】")
$knowledgeContextAt = $source.IndexOf("【知识证据】")

$ports = @()
foreach ($port in @(8093, 8094)) {
    $listener = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)[0]
    if (-not $listener) { throw "port $port is not listening" }
    $processId = [int]$listener.OwningProcess
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction Stop
    $started = (Get-Process -Id $processId -ErrorAction Stop).StartTime

    $knowledgeEnabled = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_KNOWLEDGE_ENABLED"
    $intentGate = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_KNOWLEDGE_INTENT_GATE"
    $topK = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_KNOWLEDGE_TOP_K"
    $searchMode = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_KNOWLEDGE_SEARCH_MODE"
    $mcpPrefetch = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_MCP_PREFETCH"
    $mcpTools = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_MCP_TOOLS"
    $mcpToolMode = Get-ProcessEnvironmentValue -TargetProcessId $processId -Name "BF_QA_MCP_TOOL_MODE"

    $ports += [ordered]@{
        port = $port
        pid = $processId
        process_started_at = $started.ToString("yyyy-MM-dd HH:mm:ss zzz")
        command_line = $process.CommandLine
        uses_expected_backend_path = $process.CommandLine -like "*$backend*"
        environment = [ordered]@{
            BF_QA_KNOWLEDGE_ENABLED = $knowledgeEnabled
            BF_QA_KNOWLEDGE_INTENT_GATE = $intentGate
            BF_QA_KNOWLEDGE_TOP_K = $topK
            BF_QA_KNOWLEDGE_SEARCH_MODE = $searchMode
            BF_QA_MCP_PREFETCH = $mcpPrefetch
            BF_QA_MCP_TOOLS = $mcpTools
            BF_QA_MCP_TOOL_MODE = $mcpToolMode
        }
        effective = [ordered]@{
            knowledge_enabled = Get-EffectiveBool $knowledgeEnabled $true
            knowledge_intent_gate = Get-EffectiveBool $intentGate $true
            knowledge_top_k = Get-EffectiveInt $topK 6
            knowledge_search_mode = if ([string]::IsNullOrWhiteSpace($searchMode)) { "hybrid" } else { $searchMode.Trim().ToLowerInvariant() }
            mcp_prefetch_enabled = Get-EffectiveBool $mcpPrefetch $true
            mcp_tools_enabled = Get-EffectiveBool $mcpTools $true
            mcp_tool_mode = if ([string]::IsNullOrWhiteSpace($mcpToolMode)) { "auto" } else { $mcpToolMode.Trim().ToLowerInvariant() }
        }
    }
}

$knowledgeHttp = @()
$probeQuestion = [uri]::EscapeDataString("高炉总压差升高时为什么要检查透气性")
foreach ($port in @(8093, 8094)) {
    try {
        # Force keyword mode so this read-only audit never asks the shared 11434
        # runtime to load an embedding model.
        $response = Invoke-RestMethod -Method Get -TimeoutSec 20 -Uri (
            "http://127.0.0.1:{0}/api/qa/knowledge/search?q={1}&top_k=2&mode=keyword" -f $port, $probeQuestion
        )
        $knowledgeHttp += [ordered]@{
            port = $port
            http_ok = [bool]$response.ok
            enabled = [bool]$response.enabled
            retrieval_mode = [string]$response.retrieval_mode
            evidence_count = @($response.evidence).Count
            top_titles = @($response.evidence | ForEach-Object { [string]$_.title })
            message = [string]$response.message
        }
    } catch {
        $knowledgeHttp += [ordered]@{
            port = $port
            http_ok = $false
            enabled = $false
            retrieval_mode = "keyword"
            evidence_count = 0
            top_titles = @()
            message = $_.Exception.Message
        }
    }
}

[ordered]@{
    schema = "ops.8093-8094.prompt-rag-runtime.v1"
    requirement_id = "OPS-8093-8094-PROMPT-RAG-RUNTIME-20260805"
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    backend = [ordered]@{
        path = $backend
        sha256 = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
        last_write_time = (Get-Item -LiteralPath $backend).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss zzz")
        markers = [ordered]@{
            system_prompt_template = $source.Contains("QA_SYSTEM_PROMPT_TEMPLATE =")
            project_rules_block = $source.Contains("QA_PROJECT_RULES_BLOCK =")
            build_hidden_messages = $source.Contains("def build_hidden_qa_messages(")
            prompt_formats_project_rules = $source.Contains("project_rules=QA_PROJECT_RULES_BLOCK")
            prompt_injects_knowledge = $source.Contains("knowledge_context=evidence_pack_text(knowledge_pack)")
            knowledge_intent_gate = $source.Contains("def qa_should_search_knowledge(")
            knowledge_search = $source.Contains("def qa_search_knowledge(")
            mcp_prefetch = $source.Contains("mcp_prefetch = qa_mcp_prefetch(routing_question)")
            mcp_tool_route = $source.Contains("use_mcp_tools = qa_mcp_should_use_tools(")
            fixed_rules_before_furnace_context = $fixedRulesAt -ge 0 -and $furnaceContextAt -gt $fixedRulesAt
            furnace_context_before_knowledge = $furnaceContextAt -ge 0 -and $knowledgeContextAt -gt $furnaceContextAt
        }
    }
    knowledge_backend = [ordered]@{
        path = $ragBackend
        sha256 = (Get-FileHash -LiteralPath $ragBackend -Algorithm SHA256).Hash
        postgresql_rag_tables = $ragSource.Contains("当前运行期固定使用 PostgreSQL bf_assistant.rag_* 表")
        keyword_search = $ragSource.Contains('search_mode in {"keyword", "hybrid"}')
        vector_search = $ragSource.Contains('search_mode in {"vector", "hybrid"}')
        top_k_default_6 = $ragSource.Contains("top_k: int = 6")
    }
    ports = $ports
    keyword_knowledge_http_probe = $knowledgeHttp
} | ConvertTo-Json -Depth 8
