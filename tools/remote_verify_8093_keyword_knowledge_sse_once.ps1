param([string]$PayloadPath = "")

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

# OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$temporaryPayload = "C:\Users\Administrator\AppData\Local\Temp\verify_8093_assistant_sse_once.py"
$packagePayload = Join-Path $PSScriptRoot "verify_8093_assistant_sse_once.py"
$payload = if (-not [string]::IsNullOrWhiteSpace($PayloadPath)) {
    $PayloadPath
} elseif (Test-Path -LiteralPath $packagePayload -PathType Leaf) {
    $packagePayload
} else {
    $temporaryPayload
}
$python = "C:\Program Files\Python311\python.exe"
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"
$healthLog = Join-Path $root "logs\proxy_8093.health.log"
$statePath = Join-Path $root "logs\proxy_8093.health.state.json"
$guardScript = Join-Path $root "tools\check_managed_nssm_service_health.ps1"
$configPath = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$acceptanceDir = Join-Path $root "logs\acceptance\8093_keyword_knowledge_20260805_$stamp"
$reportPath = Join-Path $acceptanceDir "assistant_keyword_knowledge_sse_once.json"
$question = "请依据知识库说明高炉透气性变差时，应观察哪些信号以及调整时要遵守什么原则？"

function Get-ListenerSnapshot {
    $ports = @(8093, 8768, 8094, 8770, 11434)
    return @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $ports -contains [int]$_.LocalPort })
}

function Get-Listener {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)]$Snapshot
    )

    $row = @($Snapshot | Where-Object { [int]$_.LocalPort -eq $Port })[0]
    if (-not $row) { throw "TCP $Port is not listening" }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Get-ProcessEnvironmentValue([int]$TargetProcessId, [string]$Name) {
    $code = @"
import sys
import psutil
print(psutil.Process(int(sys.argv[1])).environ().get(sys.argv[2], ""))
"@
    $temporary = Join-Path $env:TEMP ("bf_keyword_sse_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($temporary, $code, [Text.UTF8Encoding]::new($false))
    try {
        return (& $python $temporary $TargetProcessId $Name 2>$null) -join "`n"
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

foreach ($required in @($payload, $python, $guardScript, $configPath, $statePath, $healthLog)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file is missing: $required" }
}
$guardHashBefore = (Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash
$configHashBefore = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$config.env.BF_QA_KNOWLEDGE_SEARCH_MODE -ne "keyword") { throw "8093 config is not keyword mode" }
if ([int]$config.health.failureThreshold -ne 3 -or
    [int]$config.health.serviceNotRunningFailureThreshold -ne 1 -or
    [int]$config.health.preRestartBackoffSeconds -ne 15 -or
    [int]$config.health.restartCooldownSeconds -ne 600) {
    throw "8093 health contract changed before keyword SSE acceptance"
}

$taskBefore = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
if ($taskBefore.State.ToString() -eq "Disabled") { throw "8093 health task is disabled" }
$listenersBefore = @{}
$listenerSnapshotBefore = Get-ListenerSnapshot
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) {
    $listenersBefore[$port] = Get-Listener -Port $port -Snapshot $listenerSnapshotBefore
}
$runtimeModeBefore = Get-ProcessEnvironmentValue -TargetProcessId $listenersBefore[8093].pid -Name "BF_QA_KNOWLEDGE_SEARCH_MODE"
if ($runtimeModeBefore.Trim().ToLowerInvariant() -ne "keyword") { throw "8093 process is not running keyword mode" }

$probeQuestion = [uri]::EscapeDataString($question)
$knowledgeBefore = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$probeQuestion&top_k=2" -TimeoutSec 30
if (-not [bool]$knowledgeBefore.ok -or -not [bool]$knowledgeBefore.enabled -or
    [string]$knowledgeBefore.retrieval_mode -ne "keyword" -or @($knowledgeBefore.evidence).Count -eq 0) {
    throw "default keyword knowledge probe failed before SSE acceptance"
}

$startedAt = Get-Date
New-Item -ItemType Directory -Path $acceptanceDir -Force | Out-Null
$output = & $python -X utf8 $payload --timeout 300 --require-knowledge --question $question 2>&1
$exitCode = $LASTEXITCODE
$outputText = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
[IO.File]::WriteAllText($reportPath, $outputText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if ($exitCode -ne 0) { throw "single keyword SSE acceptance failed with exit $exitCode; report=$reportPath output=$outputText" }
$sseReport = $outputText | ConvertFrom-Json

$listenersAfter = @{}
$listenerSnapshotAfter = Get-ListenerSnapshot
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) {
    $listenersAfter[$port] = Get-Listener -Port $port -Snapshot $listenerSnapshotAfter
}
$runtimeModeAfter = Get-ProcessEnvironmentValue -TargetProcessId $listenersAfter[8093].pid -Name "BF_QA_KNOWLEDGE_SEARCH_MODE"
$taskAfter = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$knowledgeAfter = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$probeQuestion&top_k=2" -TimeoutSec 30
$processesAfter = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 20
$loadedModels = @($processesAfter.models)
$healthLinesAfterStart = @(
    Get-Content -LiteralPath $healthLog -Tail 500 -Encoding UTF8 |
        Where-Object {
            if ($_ -notmatch "^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ") { return $false }
            [datetime]::ParseExact($Matches[1], "yyyy-MM-dd HH:mm:ss", $null) -ge $startedAt.AddSeconds(-1)
        } |
        ForEach-Object { [string]$_ }
)
$restartLinesAfter = @($healthLinesAfterStart | Select-String -SimpleMatch "restart_service reason=").Count
$preparedKnowledge = $sseReport.sse.prepared_knowledge

$checks = [ordered]@{
    sse_ok = [bool]$sseReport.ok
    exactly_one_request = [int]$sseReport.request_count -eq 1
    knowledge_required_by_client = [bool]$sseReport.require_knowledge
    prepared_knowledge_enabled = [bool]$preparedKnowledge.enabled
    prepared_knowledge_not_skipped = -not [bool]$preparedKnowledge.intent.skipped
    prepared_knowledge_intent_present = -not [string]::IsNullOrWhiteSpace([string]$preparedKnowledge.intent.intent_type)
    mcp_tool_calling_disabled = -not [bool]$sseReport.sse.prepared_mcp_tool_calling
    sse_has_start = @($sseReport.sse.events) -contains "start"
    sse_has_delta = @($sseReport.sse.events) -contains "delta"
    sse_has_final = @($sseReport.sse.events) -contains "final"
    sse_has_done = @($sseReport.sse.events) -contains "done"
    answer_nonempty = [int]$sseReport.sse.answer_chars -gt 0
    process_mode_keyword_before = $runtimeModeBefore.Trim().ToLowerInvariant() -eq "keyword"
    process_mode_keyword_after = $runtimeModeAfter.Trim().ToLowerInvariant() -eq "keyword"
    default_keyword_search_before = [string]$knowledgeBefore.retrieval_mode -eq "keyword" -and @($knowledgeBefore.evidence).Count -gt 0
    default_keyword_search_after = [string]$knowledgeAfter.retrieval_mode -eq "keyword" -and @($knowledgeAfter.evidence).Count -gt 0
    health_task_enabled = $taskAfter.State.ToString() -ne "Disabled"
    health_state_clear = [int]$state.consecutiveFailures -eq 0
    no_guard_restart_during_acceptance = $restartLinesAfter -eq 0
    service_8093_pid_unchanged = $listenersBefore[8093].pid -eq $listenersAfter[8093].pid
    ws_8768_pid_unchanged = $listenersBefore[8768].pid -eq $listenersAfter[8768].pid
    preview_8094_pid_unchanged = $listenersBefore[8094].pid -eq $listenersAfter[8094].pid
    db_bridge_8770_pid_unchanged = $listenersBefore[8770].pid -eq $listenersAfter[8770].pid
    ollama_11434_pid_unchanged = $listenersBefore[11434].pid -eq $listenersAfter[11434].pid
    config_hash_unchanged = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -eq $configHashBefore
    guard_hash_unchanged = (Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash -eq $guardHashBefore
    only_approved_27b_loaded = $loadedModels.Count -eq 1 -and [string]$loadedModels[0].name -eq "chiqiong-blast-furnace:latest"
}
$failed = @($checks.Keys | Where-Object { -not [bool]$checks[$_] })
if ($failed.Count -gt 0) { throw "keyword SSE post-checks failed: $($failed -join ', '); report=$reportPath" }

[ordered]@{
    schema = "ops.8093.keyword-knowledge-sse-once.remote-acceptance.v1"
    requirement_id = "OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805"
    accepted_at = (Get-Date).ToString("o")
    report_path = $reportPath
    request_count = [int]$sseReport.request_count
    checks = $checks
    knowledge = [ordered]@{
        retrieval_mode = [string]$knowledgeAfter.retrieval_mode
        evidence_count = @($knowledgeAfter.evidence).Count
        prepared_intent = [string]$preparedKnowledge.intent.intent_type
    }
    timing_ms = [ordered]@{
        headers = $sseReport.sse.headers_ms
        first_delta = $sseReport.sse.first_delta_ms
        final = $sseReport.sse.final_ms
        total = $sseReport.sse.total_ms
        knowledge_prepare = $sseReport.sse.qa_prepare_timing_ms.knowledge
    }
    events = @($sseReport.sse.events)
    start_stages = @($sseReport.sse.start_stages)
    conversation_id = [string]$sseReport.sse.conversation_id
    answer = [string]$sseReport.sse.answer
    loaded_models_after = @($loadedModels | ForEach-Object { [string]$_.name })
    health_log_after_start = $healthLinesAfterStart
} | ConvertTo-Json -Depth 10
