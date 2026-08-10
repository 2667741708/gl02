$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$payload = "C:\Users\Administrator\AppData\Local\Temp\verify_8093_assistant_sse_once.py"
$python = "C:\Program Files\Python311\python.exe"
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"
$healthLog = Join-Path $root "logs\proxy_8093.health.log"
$statePath = Join-Path $root "logs\proxy_8093.health.state.json"
$guardScript = Join-Path $root "tools\check_managed_nssm_service_health.ps1"
$configPath = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$acceptanceDir = Join-Path $root "logs\acceptance\8093_health_guard_sse_20260804_$stamp"
$reportPath = Join-Path $acceptanceDir "assistant_sse_once.json"
$expectedGuardHash = "1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3"
$expectedConfigHash = "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE"

function Get-Listener([int]$Port) {
    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)[0]
    if (-not $row) { throw "TCP $Port is not listening" }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

foreach ($required in @($payload, $python, $guardScript, $configPath, $statePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file is missing: $required" }
}
if ((Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash -ne $expectedGuardHash) {
    throw "deployed guard script hash changed before SSE acceptance"
}
if ((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -ne $expectedConfigHash) {
    throw "deployed 8093 config hash changed before SSE acceptance"
}

$taskBefore = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
if ($taskBefore.State -eq "Disabled") { throw "8093 health task is disabled" }
$listenersBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersBefore[$port] = Get-Listener $port }
$startedAt = Get-Date
$restartLinesBefore = @(
    Get-Content -LiteralPath $healthLog -Tail 500 -Encoding UTF8 |
        Select-String -SimpleMatch "restart_service reason="
).Count

New-Item -ItemType Directory -Path $acceptanceDir -Force | Out-Null
$output = & $python -X utf8 $payload --timeout 300 2>&1
$exitCode = $LASTEXITCODE
$outputText = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
[IO.File]::WriteAllText($reportPath, $outputText + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
if ($exitCode -ne 0) { throw "single SSE acceptance failed with exit $exitCode; report=$reportPath output=$outputText" }
$sseReport = $outputText | ConvertFrom-Json

$listenersAfter = @{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersAfter[$port] = Get-Listener $port }
$taskAfter = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
$healthLinesAfterStart = @(
    Get-Content -LiteralPath $healthLog -Tail 500 -Encoding UTF8 |
        Where-Object {
            if ($_ -notmatch "^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ") { return $false }
            [datetime]::ParseExact($Matches[1], "yyyy-MM-dd HH:mm:ss", $null) -ge $startedAt.AddSeconds(-1)
        } |
        ForEach-Object { [string]$_ }
)
$restartLinesAfter = @($healthLinesAfterStart | Select-String -SimpleMatch "restart_service reason=").Count

$checks = [ordered]@{
    sse_ok = [bool]$sseReport.ok
    exactly_one_request = [int]$sseReport.request_count -eq 1
    sse_has_start = @($sseReport.sse.events) -contains "start"
    sse_has_delta = @($sseReport.sse.events) -contains "delta"
    sse_has_final = @($sseReport.sse.events) -contains "final"
    sse_has_done = @($sseReport.sse.events) -contains "done"
    answer_nonempty = [int]$sseReport.sse.answer_chars -gt 0
    conversation_id_present = -not [string]::IsNullOrWhiteSpace([string]$sseReport.sse.conversation_id)
    health_task_enabled = $taskAfter.State -ne "Disabled"
    health_state_clear = [int]$state.consecutiveFailures -eq 0
    no_guard_restart_during_acceptance = $restartLinesAfter -eq 0
    service_8093_pid_unchanged = $listenersBefore[8093].pid -eq $listenersAfter[8093].pid
    ws_8768_pid_unchanged = $listenersBefore[8768].pid -eq $listenersAfter[8768].pid
    preview_8094_pid_unchanged = $listenersBefore[8094].pid -eq $listenersAfter[8094].pid
    db_bridge_8770_pid_unchanged = $listenersBefore[8770].pid -eq $listenersAfter[8770].pid
    ollama_11434_pid_unchanged = $listenersBefore[11434].pid -eq $listenersAfter[11434].pid
}
$failed = @($checks.Keys | Where-Object { -not [bool]$checks[$_] })
if ($failed.Count -gt 0) { throw "SSE post-checks failed: $($failed -join ', '); report=$reportPath" }

[ordered]@{
    schema = "ops.8093.assistant-sse-once.remote-acceptance.v1"
    requirement_id = "OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804"
    accepted_at = (Get-Date).ToString("o")
    report_path = $reportPath
    checks = $checks
    timing_ms = [ordered]@{
        headers = $sseReport.sse.headers_ms
        first_delta = $sseReport.sse.first_delta_ms
        final = $sseReport.sse.final_ms
        total = $sseReport.sse.total_ms
    }
    events = @($sseReport.sse.events)
    start_stages = @($sseReport.sse.start_stages)
    conversation_id = [string]$sseReport.sse.conversation_id
    answer = [string]$sseReport.sse.answer
    loaded_models_after = @($sseReport.runtime_after.loaded_models)
    health_log_restart_lines_before_tail = $restartLinesBefore
    health_log_after_start = $healthLinesAfterStart
} | ConvertTo-Json -Depth 10
