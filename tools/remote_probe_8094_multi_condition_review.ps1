$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$backend = Join-Path $frontend "智能助手\backend"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

function Get-ListenerInfo {
    param([Parameter(Mandatory = $true)][int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) {
        return [ordered]@{ port = $Port; listening = $false; pid = $null; commandLine = $null }
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    return [ordered]@{
        port = $Port
        listening = $true
        pid = [int]$listener.OwningProcess
        commandLine = if ($process) { [string]$process.CommandLine } else { $null }
    }
}

function Get-FileEvidence {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ path = $Path; exists = $false; sha256 = $null; length = 0 }
    }
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        path = $Path
        exists = $true
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        length = [int64]$item.Length
    }
}

function Get-HttpEvidence {
    param([Parameter(Mandatory = $true)][int]$Port)
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?probe=multi_condition_20260805" -TimeoutSec 30
    $content = [string]$response.Content
    return [ordered]@{
        status = [int]$response.StatusCode
        length = $content.Length
        multiConditionMarker = $content.Contains("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805")
        cadR2Marker = $content.Contains("BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2")
    }
}

$html8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$html8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$runner8094 = Join-Path $root "tools\run_22012_8094_preview.ps1"
$sharedProxy = Join-Path $backend "ollama_proxy_server.py"
$isolatedProxy = Join-Path $backend "ollama_proxy_server_8094.py"
$modelReview = Join-Path $backend "diagnosis_model_review.py"
$adapter = Join-Path $root "自动诊断服务\recommendation_adapter.py"
$bridge = Join-Path $root "自动诊断服务\local_pg_ws_bridge.py"
$html8094Text = Get-Content -LiteralPath $html8094 -Raw -Encoding UTF8
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop

[ordered]@{
    checkedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    task = [ordered]@{
        state = $task.State.ToString()
        lastRunTime = $taskInfo.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")
        lastResult = [int]$taskInfo.LastTaskResult
    }
    listeners = @(
        Get-ListenerInfo -Port 8093
        Get-ListenerInfo -Port 8094
        Get-ListenerInfo -Port 8768
        Get-ListenerInfo -Port 8769
        Get-ListenerInfo -Port 8770
        Get-ListenerInfo -Port 11434
    )
    http = [ordered]@{
        port8093 = Get-HttpEvidence -Port 8093
        port8094 = Get-HttpEvidence -Port 8094
    }
    files = [ordered]@{
        html8093 = Get-FileEvidence -Path $html8093
        html8094 = Get-FileEvidence -Path $html8094
        runner8094 = Get-FileEvidence -Path $runner8094
        sharedProxy = Get-FileEvidence -Path $sharedProxy
        isolatedProxy = Get-FileEvidence -Path $isolatedProxy
        modelReview = Get-FileEvidence -Path $modelReview
        recommendationAdapter = Get-FileEvidence -Path $adapter
        wsBridge = Get-FileEvidence -Path $bridge
    }
    contracts = [ordered]@{
        optimizationCockpit = $html8094Text.Contains("function OptimizationEngineCockpitLayout")
        optimizationAssignmentCount = ([regex]::Matches($html8094Text, "OptimizationTab\s*=\s*OptimizationEngineCockpitLayout;")).Count
        diagnosisKeys = $html8094Text.Contains("const DIAG_KEYS")
        diagnosisReader = $html8094Text.Contains("function getDiag")
        confidenceNormalizer = $html8094Text.Contains("function bfRecommendationConfidence")
        multiConditionMarker = $html8094Text.Contains("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805")
        defaultWs8768 = $html8094Text.Contains("get('ws_port') || '8768'")
        defaultWs8769 = $html8094Text.Contains("get('ws_port') || '8769'")
        previewWsTaskExists = [bool](Get-ScheduledTask -TaskPath $taskPath -TaskName "V4PreviewWs8769" -ErrorAction SilentlyContinue)
    }
} | ConvertTo-Json -Depth 8 -Compress
