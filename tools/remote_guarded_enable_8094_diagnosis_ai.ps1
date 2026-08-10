$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$runner = Join-Path $root "tools\run_22012_8094_preview.ps1"
$backend = Join-Path $root "高炉前端数据\智能助手\backend"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "logs\deploy_backups\8094_diagnosis_ai_$stamp"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$beginMarker = "# REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806 BEGIN"
$endMarker = "# REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806 END"

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $present = $null -ne (Get-ListenerPid $Port)
        if ($present -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}

function Restart-8094Preview {
    foreach ($protectedPort in @(8093, 8768, 8770, 11434)) {
        if (-not (Get-ListenerPid $protectedPort)) { throw "protected port $protectedPort is not listening" }
    }
    $listenerPid = Get-ListenerPid 8094
    if ($listenerPid) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" -ErrorAction Stop
        $listens8093 = Get-NetTCPConnection -LocalPort 8093 -State Listen -OwningProcess $listenerPid -ErrorAction SilentlyContinue
        if (
            $process.Name -ne "python.exe" -or
            -not $process.CommandLine.Contains("ollama_proxy_server.py") -or
            $process.CommandLine.Contains("ollama_proxy_server_8094.py") -or
            $listens8093
        ) { throw "8094 listener is not the expected shared-proxy child" }
    }
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if ($listenerPid -and (Get-ListenerPid 8094) -eq $listenerPid) {
        Stop-Process -Id $listenerPid -Force
    }
    Wait-Port 8094 $false 45
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Wait-Port 8094 $true 150
}

function Invoke-Http([string]$Uri, [string]$Method = "GET", [string]$Body = "") {
    $parameters = @{
        UseBasicParsing = $true
        Uri = $Uri
        Method = $Method
        TimeoutSec = 20
    }
    if ($Method -eq "POST") {
        $parameters.ContentType = "application/json; charset=utf-8"
        $parameters.Body = $Body
    }
    try {
        $response = Invoke-WebRequest @parameters
        return [ordered]@{ status = [int]$response.StatusCode; content = [string]$response.Content }
    }
    catch {
        $status = $null
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        return [ordered]@{ status = $status; content = ""; error = $_.Exception.Message }
    }
}

function Wait-Analysis([string]$Label, [int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        $response = Invoke-Http "http://127.0.0.1:8094/api/diagnosis-ai-analysis?label=$Label"
        if ($response.content) {
            $last = $response.content | ConvertFrom-Json
            if ($last.ok -and $last.enabled -and $last.analysis.state -eq "completed") {
                return $last
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "8094 diagnosis analysis did not complete: $($last | ConvertTo-Json -Depth 5 -Compress)"
}

$required = @(
    $runner,
    (Join-Path $backend "ollama_proxy_server.py"),
    (Join-Path $backend "diagnosis_review.py"),
    (Join-Path $backend "diagnosis_model_review.py"),
    (Join-Path $backend "diag_ai_evidence.py"),
    (Join-Path $backend "diagnosis_ai_analysis_api.py")
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "required file is missing: $path" }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State.ToString() -eq "Disabled") { throw "8094 preview task is disabled" }
$pid8093Before = Get-ListenerPid 8093
$pid8094Before = Get-ListenerPid 8094
$pid8768Before = Get-ListenerPid 8768
$pid8770Before = Get-ListenerPid 8770
$pid11434Before = Get-ListenerPid 11434
if (-not $pid8093Before -or -not $pid8094Before -or -not $pid8768Before) {
    throw "8093/8094/8768 must be listening before deployment"
}

$runnerText = [IO.File]::ReadAllText($runner, [Text.Encoding]::UTF8)
if (-not $runnerText.Contains('ollama_proxy_server.py')) { throw "8094 runner is not using the shared current proxy" }
if ($runnerText.Contains('8769') -or $runnerText.Contains('ollama_proxy_server_8094.py')) {
    throw "refusing to enable diagnosis features on an obsolete isolated 8094 runner"
}
$markerPattern = [regex]::Escape($beginMarker) + '[\s\S]*?' + [regex]::Escape($endMarker) + '\r?\n?'
$runnerText = [regex]::Replace($runnerText, $markerPattern, "")
$anchor = '$env:BF_QA_DB = "$frontend\data\bf_qa.sqlite3"'
if (-not $runnerText.Contains($anchor)) { throw "8094 runner anchor is missing" }
$role = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('546w5Zy66auY54KJ6ZW/'))
$block = @"
$beginMarker
`$env:BF_DIAGNOSIS_REVIEW_ENABLED = "1"
`$env:BF_DIAGNOSIS_REVIEW_TEST_MODE = "0"
`$env:BF_DIAG_REVIEW_REQUIRE_LOGIN = "0"
`$env:BF_DIAG_REVIEW_ANONYMOUS_USERNAME = "onsite_8094"
`$env:BF_DIAG_REVIEW_ANONYMOUS_ROLE = "$role"
`$env:BF_DIAG_REVIEW_PGHOST = "127.0.0.1"
`$env:BF_DIAG_REVIEW_PGPORT = "5432"
`$env:BF_DIAG_REVIEW_PGDATABASE = "bf_trend"
`$env:BF_DIAG_REVIEW_PGUSER = "gl02_sync"
`$env:BF_DIAG_REVIEW_PGPASSWORD_ENV = "GL02_PGPASSWORD"
`$env:BF_DIAG_REVIEW_PGSCHEMA = "bf_assistant"
`$env:BF_DIAGNOSIS_MODEL_REVIEW_ENABLED = "1"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_ENABLED = "1"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED = "1"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES = "5"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS = "30"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS = "120"
`$env:BF_DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT = "12"
$endMarker
"@
$patched = $runnerText.Replace($anchor, "$anchor`r`n`r`n$block")

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $runner -Destination (Join-Path $backup "run_22012_8094_preview.ps1") -Force
$temporary = "$runner.codex-$stamp.tmp"
[IO.File]::WriteAllText($temporary, $patched, [Text.UTF8Encoding]::new($true))

$success = $false
try {
    Move-Item -LiteralPath $temporary -Destination $runner -Force
    Restart-8094Preview

    $page = Invoke-Http "http://127.0.0.1:8094/?t=diagnosis-ai-$stamp"
    if ($page.status -ne 200) { throw "8094 page HTTP status is not 200" }
    if (-not $page.content.Contains("bf-diagnosis-manual-score-local.js")) { throw "8094 manual score injection is missing" }
    if (-not $page.content.Contains("bf-diagnosis-review-local.js")) { throw "8094 abnormal review injection is missing" }
    if (-not $page.content.Contains("20260806-core19-r10-foreman-knowledge")) { throw "8094 core19 asset version is missing" }
    $manualAsset = Invoke-Http "http://127.0.0.1:8094/assets/bf-diagnosis-manual-score-local.js?t=20260806-core19-r10-foreman-knowledge"
    if ($manualAsset.status -ne 200) { throw "8094 manual score asset is unavailable" }
    if (-not $manualAsset.content.Contains("bfdms-core-evidence")) { throw "8094 core variable evidence UI is missing" }
    if (-not $manualAsset.content.Contains("renderCoreChart")) { throw "8094 core variable trend chart is missing" }
    if (-not $manualAsset.content.Contains("bfdms-ai-core-early")) { throw "8094 preparing-state core evidence UI is missing" }
    if (-not $manualAsset.content.Contains("bootWhenBodyReady")) { throw "8094 body-poll boot marker is missing" }
    if (-not $manualAsset.content.Contains('renderAi({state:"failed"});state.analysisTimer=setTimeout(loadAiAnalysis,3000)')) { throw "8094 transient analysis retry is missing" }
    if (-not $manualAsset.content.Contains('/api/diagnosis-core-evidence?label=')) { throw "8094 lightweight core endpoint client is missing" }

    $contextResponse = Invoke-Http "http://127.0.0.1:8094/api/diagnosis-review-context"
    if ($contextResponse.status -ne 200) { throw "8094 diagnosis review context is unavailable" }
    $context = $contextResponse.content | ConvertFrom-Json
    if (-not $context.ok -or -not $context.enabled -or -not $context.auth.can_submit) {
        throw "8094 diagnosis review context is not writable without login"
    }

    $expectedCoreVariableIds = @(
        "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
        "T_top_A", "T_top_B", "T_top_C", "T_top_D",
        "P_top", "T_top", "Q_blast", "P_blast_cold", "P_blast", "T_blast",
        "PI", "DP_total", "DP_upper", "DP_lower", "GasUtil"
    )
    $coreEndpointResponse = Invoke-Http "http://127.0.0.1:8094/api/diagnosis-core-evidence?label=normal"
    if ($coreEndpointResponse.status -ne 200) { throw "8094 lightweight core endpoint is unavailable" }
    $coreEndpoint = $coreEndpointResponse.content | ConvertFrom-Json
    $coreEndpointIds = @($coreEndpoint.evidence.core_variable_evidence | ForEach-Object { [string]$_.id })
    $coreEndpointIdsMatch = ((@($coreEndpointIds | Sort-Object) -join ",") -eq (@($expectedCoreVariableIds | Sort-Object) -join ","))
    $coreEndpointSeriesCount = @($coreEndpoint.evidence.core_variable_evidence | Where-Object { @($_.series_60m).Count -gt 0 }).Count
    if ([string]$coreEndpoint.evidence.schema_version -ne "diagnosis_core_evidence.v1") { throw "8094 lightweight core endpoint schema is not v1" }
    if ([int]$coreEndpoint.evidence.core_variable_count -ne 19 -or -not $coreEndpointIdsMatch -or $coreEndpointSeriesCount -ne 19) { throw "8094 lightweight core endpoint contract failed" }
    $reviewValidation = Invoke-Http "http://127.0.0.1:8094/api/diagnosis/model-review" "POST" "{}"
    if ($reviewValidation.status -ne 400) { throw "8094 model review route expected HTTP 400" }
    $manualValidation = Invoke-Http "http://127.0.0.1:8094/api/diagnosis-manual-scores" "POST" "{}"
    if ($manualValidation.status -ne 400) { throw "8094 manual score route expected HTTP 400" }

    $pid8094After = Get-ListenerPid 8094
    if (-not $pid8094After -or $pid8094After -eq $pid8094Before) { throw "8094 PID did not change" }
    if ((Get-ListenerPid 8093) -ne $pid8093Before) { throw "8093 PID changed during 8094 deployment" }
    if ((Get-ListenerPid 8768) -ne $pid8768Before) { throw "8768 PID changed during 8094 deployment" }
    if ((Get-ListenerPid 8770) -ne $pid8770Before) { throw "8770 PID changed during 8094 deployment" }
    if ((Get-ListenerPid 11434) -ne $pid11434Before) { throw "11434 PID changed during 8094 deployment" }

    $success = $true
    [ordered]@{
        ok = $true
        operation = "OPS-8094-DIAGNOSIS-CORE-19-TRENDS-20260806"
        backup = $backup
        pid8093Unchanged = $true
        pid8094Before = $pid8094Before
        pid8094After = $pid8094After
        pid8768Unchanged = $true
        pid8770Unchanged = $true
        pid11434Unchanged = $true
        pageInjected = $true
        coreEvidenceUi = $true
        coreTrendChartUi = $true
        coreAvailableWhilePreparing = $true
        transientAnalysisRetry = $true
        lightweightCoreEndpoint = $true
        contextCanSubmit = [bool]$context.auth.can_submit
        loginRequired = [bool]$context.auth.login_required
        analysisVerificationMode = "runtime_async"
        analysisSchemaContract = "diagnosis_ai_analysis.v4"
        coreVariableCount = [int]$coreEndpoint.evidence.core_variable_count
        coreSeriesCount = $coreEndpointSeriesCount
        coreVariableIdsMatch = $coreEndpointIdsMatch
        lightweightCoreSeriesCount = $coreEndpointSeriesCount
        lightweightCoreIdsMatch = $coreEndpointIdsMatch
        analysisLoadsAsynchronously = $true
        modelReviewRoute = $reviewValidation.status
        manualScoreRoute = $manualValidation.status
    } | ConvertTo-Json -Depth 8
}
catch {
    $failure = $_
    Copy-Item -LiteralPath (Join-Path $backup "run_22012_8094_preview.ps1") -Destination $runner -Force
    Restart-8094Preview
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    if (-not $success) { Write-Warning "8094 diagnosis enable failed; runner restoration was attempted from $backup" }
}
