param(
    [string]$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    [string]$SimulationInputPath = "",
    [int]$EndpointTimeoutSeconds = 8
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805

function Write-JsonResult {
    param([Parameter(Mandatory = $true)]$Value)

    $Value | ConvertTo-Json -Depth 12
}

function Get-ServiceRow {
    param([Parameter(Mandatory = $true)][string]$Name)

    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        return [ordered]@{ name = $Name; exists = $false; status = $null }
    }
    return [ordered]@{
        name = $Name
        exists = $true
        status = $service.Status.ToString()
    }
}

function Get-ListenerRow {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)]$Snapshot
    )

    $row = @($Snapshot | Where-Object { [int]$_.LocalPort -eq $Port }) | Select-Object -First 1
    return [ordered]@{
        port = $Port
        listening = $null -ne $row
        pid = if ($row) { [int]$row.OwningProcess } else { $null }
    }
}

function Get-UnavailableEndpointRow {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Uri
    )

    return [ordered]@{
        name = $Name
        uri = $Uri
        ok = $false
        status_code = $null
        elapsed_ms = 0
        content = $null
        error = "TCP 8093 is not listening"
    }
}

function Get-EndpointRow {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = $EndpointTimeoutSeconds
    )

    $started = Get-Date
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSeconds
        $content = $response.Content
        try { $content = $content | ConvertFrom-Json } catch { }
        return [ordered]@{
            name = $Name
            uri = $Uri
            ok = $true
            status_code = [int]$response.StatusCode
            elapsed_ms = [int]((Get-Date) - $started).TotalMilliseconds
            content = $content
            error = $null
        }
    } catch {
        return [ordered]@{
            name = $Name
            uri = $Uri
            ok = $false
            status_code = $null
            elapsed_ms = [int]((Get-Date) - $started).TotalMilliseconds
            content = $null
            error = $_.Exception.Message
        }
    }
}

function Get-ProcessEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][int]$TargetProcessId,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $python = "C:\Program Files\Python311\python.exe"
    $code = @"
import sys
import psutil

try:
    value = psutil.Process(int(sys.argv[1])).environ().get(sys.argv[2], "")
    print(value)
except Exception as exc:
    print("ENV_ERROR:" + str(exc))
"@
    $temporary = Join-Path $env:TEMP ("assistant_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($temporary, $code, [Text.UTF8Encoding]::new($false))
    try {
        return ((& $python -X utf8 $temporary $TargetProcessId $Name 2>$null) -join "`n").Trim()
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

if (-not [string]::IsNullOrWhiteSpace($SimulationInputPath)) {
    $simulation = Get-Content -LiteralPath $SimulationInputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $listenerRows = @(
        foreach ($property in $simulation.listeners.PSObject.Properties) {
            [ordered]@{
                port = [int]$property.Name
                listening = [bool]$property.Value.listening
                pid = if ($null -ne $property.Value.pid) { [int]$property.Value.pid } else { $null }
            }
        }
    )
    $simulatedResult = [ordered]@{
        schema = "ops.8093.assistant-auto-diagnose.simulation.v1"
        collected_at = (Get-Date).ToString("o")
        services = @($simulation.services)
        listeners = $listenerRows
        endpoints = @($simulation.endpoints)
        config = $simulation.config
        guard = $simulation.guard
        logs = $simulation.logs
    }
    Write-JsonResult -Value $simulatedResult
    exit 0
}

$configPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$ollamaConfigPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFOllama11434.json"
$guardScriptPath = Join-Path $ProjectRoot "tools\check_managed_nssm_service_health.ps1"
$proxyPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$ragPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\bf_knowledge_rag.py"
$assistantPgPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\assistant_pg.py"
$frontendPath = Join-Path $ProjectRoot "高炉前端数据\frontend_dashboard_v3.server.html"
$statePath = Join-Path $ProjectRoot "logs\proxy_8093.health.state.json"
$healthLogPath = Join-Path $ProjectRoot "logs\proxy_8093.health.log"
$outLogPath = Join-Path $ProjectRoot "logs\proxy_8093.service.out.log"
$errLogPath = Join-Path $ProjectRoot "logs\proxy_8093.service.err.log"
$runnerLogPath = Join-Path $ProjectRoot "logs\proxy_8093.service.runner.log"
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"

$requiredFiles = @($configPath, $ollamaConfigPath, $guardScriptPath, $proxyPath, $ragPath, $assistantPgPath, $frontendPath)
foreach ($requiredFile in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "required diagnostic file is missing: $requiredFile"
    }
}

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ollamaConfig = Get-Content -LiteralPath $ollamaConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$services = @(
    Get-ServiceRow -Name "BFV4PreviewProxy8093"
    Get-ServiceRow -Name "BFOllama11434"
    Get-ServiceRow -Name "BFV4PreviewWs8768"
)
$postgresServices = @(
    Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue |
        ForEach-Object {
            [ordered]@{ name = $_.Name; exists = $true; status = $_.Status.ToString() }
        }
)
$targetPorts = @(5432, 8093, 8094, 8768, 8770, 11434)
$listenerSnapshot = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $targetPorts -contains [int]$_.LocalPort })
$listeners = @(
    foreach ($port in $targetPorts) {
        Get-ListenerRow -Port $port -Snapshot $listenerSnapshot
    }
)
$listener8093 = @($listeners | Where-Object { $_.port -eq 8093 })[0]
$listener11434 = @($listeners | Where-Object { $_.port -eq 11434 })[0]

$runtime8093 = [ordered]@{
    pid = $listener8093.pid
    knowledge_search_mode = $null
    ollama_base_url = $null
    allowed_loaded_models = $null
    pg_pool_enabled = $null
    pg_pool_min_size = $null
    pg_pool_max_size = $null
    pg_pool_timeout_seconds = $null
}
if ($listener8093.listening) {
    $runtime8093.knowledge_search_mode = Get-ProcessEnvironmentValue $listener8093.pid "BF_QA_KNOWLEDGE_SEARCH_MODE"
    $runtime8093.ollama_base_url = Get-ProcessEnvironmentValue $listener8093.pid "OLLAMA_BASE_URL"
    $runtime8093.allowed_loaded_models = Get-ProcessEnvironmentValue $listener8093.pid "BF_ALLOWED_LOADED_MODELS"
    $runtime8093.pg_pool_enabled = Get-ProcessEnvironmentValue $listener8093.pid "BF_ASSISTANT_PG_POOL_ENABLED"
    $runtime8093.pg_pool_min_size = Get-ProcessEnvironmentValue $listener8093.pid "BF_ASSISTANT_PG_POOL_MIN_SIZE"
    $runtime8093.pg_pool_max_size = Get-ProcessEnvironmentValue $listener8093.pid "BF_ASSISTANT_PG_POOL_MAX_SIZE"
    $runtime8093.pg_pool_timeout_seconds = Get-ProcessEnvironmentValue $listener8093.pid "BF_ASSISTANT_PG_POOL_TIMEOUT_SECONDS"
    $process8093 = Get-Process -Id $listener8093.pid -ErrorAction SilentlyContinue
    if ($process8093) {
        $runtime8093["thread_count"] = @($process8093.Threads).Count
        $runtime8093["handle_count"] = [int]$process8093.HandleCount
        $runtime8093["working_set_mb"] = [Math]::Round($process8093.WorkingSet64 / 1MB, 1)
        $runtime8093["cpu_seconds"] = [Math]::Round($process8093.CPU, 1)
    }
}

$runtime11434 = [ordered]@{
    pid = $listener11434.pid
    max_loaded_models = $null
    keep_alive = $null
}
if ($listener11434.listening) {
    $runtime11434.max_loaded_models = Get-ProcessEnvironmentValue $listener11434.pid "OLLAMA_MAX_LOADED_MODELS"
    $runtime11434.keep_alive = Get-ProcessEnvironmentValue $listener11434.pid "OLLAMA_KEEP_ALIVE"
}

$knowledgeQuestion = [uri]::EscapeDataString("高炉总压差升高时为什么要检查透气性")
$assistantStatusUri = "http://127.0.0.1:8093/api/ollama/status"
$knowledgeUri = "http://127.0.0.1:8093/api/qa/knowledge/search?q=$knowledgeQuestion&top_k=2"
if ($listener8093.listening) {
    $assistantStatus = Get-EndpointRow -Name "assistant_status" -Uri $assistantStatusUri
    $knowledgeStatus = Get-EndpointRow -Name "default_knowledge_search" -Uri $knowledgeUri -TimeoutSeconds 20
} else {
    $assistantStatus = Get-UnavailableEndpointRow -Name "assistant_status" -Uri $assistantStatusUri
    $knowledgeStatus = Get-UnavailableEndpointRow -Name "default_knowledge_search" -Uri $knowledgeUri
}
$endpoints = @(
    $assistantStatus
    Get-EndpointRow -Name "ollama_processes" -Uri "http://127.0.0.1:11434/api/ps"
    $knowledgeStatus
)

$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
$serviceEvents = @(
    Get-WinEvent -FilterHashtable @{
        LogName = "System"
        ProviderName = "Service Control Manager"
        StartTime = (Get-Date).AddHours(-2)
    } -MaxEvents 500 -ErrorAction SilentlyContinue |
        Where-Object { $_.Message -like "*BFV4PreviewProxy8093*" -or $_.Message -like "*Blast Furnace V4 Preview Proxy 8093*" } |
        Select-Object -First 12 |
        ForEach-Object {
            [ordered]@{
                time = $_.TimeCreated.ToString("o")
                id = [int]$_.Id
                level = $_.LevelDisplayName
                message = [string]$_.Message
            }
        }
)
$healthTail = @()
if (Test-Path -LiteralPath $healthLogPath -PathType Leaf) {
    $healthTail = @(Get-Content -LiteralPath $healthLogPath -Tail 80 -Encoding UTF8)
}
$outTail = @()
if (Test-Path -LiteralPath $outLogPath -PathType Leaf) {
    $outTail = @(Get-Content -LiteralPath $outLogPath -Tail 1000 -Encoding UTF8)
}
$errTail = @()
if (Test-Path -LiteralPath $errLogPath -PathType Leaf) {
    $errTail = @(Get-Content -LiteralPath $errLogPath -Tail 600 -Encoding UTF8)
}
$runnerTail = @()
if (Test-Path -LiteralPath $runnerLogPath -PathType Leaf) {
    $runnerTail = @(Get-Content -LiteralPath $runnerLogPath -Tail 20 -Encoding UTF8)
}
$errorPattern = "Error|Exception|Timeout|timed out|BrokenPipe|ConnectionReset|RemoteDisconnected|embedding|nomic|psycopg|Traceback"
$errorMatches = @(
    $errTail |
        Select-String -Pattern $errorPattern |
        Select-Object -Last 40 |
        ForEach-Object { $_.Line }
)
$qaRequests = @(
    $outTail |
        Select-String -SimpleMatch "POST /api/qa/chat" |
        Select-Object -Last 20 |
        ForEach-Object { $_.Line }
)
$httpRequests = @(
    $outTail |
        Select-String -Pattern '"(?:GET|POST|OPTIONS) /' |
        Select-Object -Last 100 |
        ForEach-Object { $_.Line }
)
$restartLines = @(
    $healthTail |
        Select-String -SimpleMatch "restart_service" |
        Select-Object -Last 20 |
        ForEach-Object { $_.Line }
)

$state = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
}

$result = [ordered]@{
    schema = "ops.8093.assistant-auto-diagnose.v1"
    requirement_id = "OPS-8093-ASSISTANT-AUTO-RECOVERY-20260805"
    collected_at = (Get-Date).ToString("o")
    project_root = $ProjectRoot
    services = $services
    postgres_services = $postgresServices
    listeners = $listeners
    endpoints = $endpoints
    runtime = [ordered]@{
        assistant_8093 = $runtime8093
        ollama_11434 = $runtime11434
    }
    files = [ordered]@{
        proxy_sha256 = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
        rag_sha256 = (Get-FileHash -LiteralPath $ragPath -Algorithm SHA256).Hash
        assistant_pg_sha256 = (Get-FileHash -LiteralPath $assistantPgPath -Algorithm SHA256).Hash
        frontend_sha256 = (Get-FileHash -LiteralPath $frontendPath -Algorithm SHA256).Hash
        frontend_fetch_resilience = [bool](Select-String -LiteralPath $frontendPath -SimpleMatch "OPS-8093-QA-FETCH-RESILIENCE-20260806" -Quiet)
    }
    config = [ordered]@{
        path = $configPath
        sha256 = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        service_name = [string]$config.serviceName
        knowledge_search_mode = [string]$config.env.BF_QA_KNOWLEDGE_SEARCH_MODE
        health = [ordered]@{
            failure_threshold = [int]$config.health.failureThreshold
            service_down_threshold = [int]$config.health.serviceNotRunningFailureThreshold
            pre_restart_backoff_seconds = [int]$config.health.preRestartBackoffSeconds
            restart_cooldown_seconds = [int]$config.health.restartCooldownSeconds
        }
        ollama_max_loaded_models = [string]$ollamaConfig.env.OLLAMA_MAX_LOADED_MODELS
        ollama_keep_alive = [string]$ollamaConfig.env.OLLAMA_KEEP_ALIVE
    }
    guard = [ordered]@{
        script_path = $guardScriptPath
        script_sha256 = (Get-FileHash -LiteralPath $guardScriptPath -Algorithm SHA256).Hash
        task_state = if ($task) { $task.State.ToString() } else { $null }
        last_task_result = if ($taskInfo) { [long]$taskInfo.LastTaskResult } else { $null }
        state = $state
    }
    logs = [ordered]@{
        qa_requests = $qaRequests
        http_requests = $httpRequests
        error_matches = $errorMatches
        guard_restarts = $restartLines
        service_events = $serviceEvents
        health_tail = @($healthTail | ForEach-Object { [string]$_ })
        stderr_tail = @($errTail | Select-Object -Last 80 | ForEach-Object { [string]$_ })
        runner_tail = @($runnerTail | ForEach-Object { [string]$_ })
    }
}

Write-JsonResult -Value $result
