$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$wsServiceName = 'BFV4PreviewWs8768'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$payloadRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\diagnosis_ai_analysis_$stamp"

$payloads = @(
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_review.py'); source = (Join-Path $payloadRoot 'diagnosis_review.py') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_model_review.py'); source = (Join-Path $payloadRoot 'diagnosis_model_review.py') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\智能助手\backend\diag_ai_evidence.py'); source = (Join-Path $payloadRoot 'diag_ai_evidence.py') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_ai_analysis_api.py'); source = (Join-Path $payloadRoot 'diagnosis_ai_analysis_api.py') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'); source = (Join-Path $payloadRoot 'ollama_proxy_server.py') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-review-local.js'); source = (Join-Path $payloadRoot 'bf-diagnosis-review-local.js') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-review-local.css'); source = (Join-Path $payloadRoot 'bf-diagnosis-review-local.css') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-manual-score-local.js'); source = (Join-Path $payloadRoot 'bf-diagnosis-manual-score-local.js') }
    [pscustomobject]@{ target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-manual-score-local.css'); source = (Join-Path $payloadRoot 'bf-diagnosis-manual-score-local.css') }
)

function Wait-ServiceState {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$DesiredState,
        [int]$TimeoutSeconds = 20
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
}

function Wait-Port {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][bool]$Listening,
        [int]$TimeoutSeconds = 20
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return $present }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening within ${TimeoutSeconds}s"
}

function Get-HttpBodyHash([string]$Uri) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($response.Content)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [ordered]@{
            status = [int]$response.StatusCode
            sha256 = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
            body_length = $response.Content.Length
        }
    }
    finally { $sha.Dispose() }
}

function Get-HttpStatus([string]$Uri, [string]$Method = 'GET', [string]$Body = '') {
    try {
        $params = @{
            UseBasicParsing = $true
            Uri = $Uri
            Method = $Method
            TimeoutSec = 8
        }
        if ($Method -eq 'POST') {
            $params.ContentType = 'application/json; charset=utf-8'
            $params.Body = $Body
        }
        $response = Invoke-WebRequest @params
        return [int]$response.StatusCode
    }
    catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}

function Wait-DiagnosisAiAnalysis {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$TimeoutSeconds = 300
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=$Label" -TimeoutSec 12
            $last = $response.Content | ConvertFrom-Json
            if ($last.ok -and $last.enabled -and $last.analysis.state -eq 'completed') {
                return $last
            }
        }
        catch {
            $last = [pscustomobject]@{ error = $_.Exception.Message }
        }
        Start-Sleep -Seconds 3
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "five-minute diagnosis AI analysis did not complete: $($last | ConvertTo-Json -Depth 5 -Compress)"
}

function Wait-DiagnosisReviewContext {
    param([int]$TimeoutSeconds = 90)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = $null
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/diagnosis-review-context?t=20260805' -TimeoutSec 12
            $last = $response.Content | ConvertFrom-Json
            if ($last.ok -and $last.enabled) { return $last }
        }
        catch {
            $last = [pscustomobject]@{ error = $_.Exception.Message }
        }
        Start-Sleep -Seconds 3
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "diagnosis review context did not become ready: $($last | ConvertTo-Json -Depth 5 -Compress)"
}

function Set-ObjectProperty($Object, [string]$Name, [object]$Value) {
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { $property.Value = $Value }
    else { $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value }
}

function Write-JsonAtomically([string]$Path, $Value) {
    $temporary = "$Path.codex-$stamp.tmp"
    $json = $Value | ConvertTo-Json -Depth 12
    [System.IO.File]::WriteAllText($temporary, $json, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Install-Payload([string]$Source, [string]$Target) {
    $targetDirectory = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $targetDirectory)) {
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    }
    $temporary = "$Target.codex-$stamp.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Restore-Deployment {
    param([array]$Manifest)
    foreach ($entry in $Manifest) {
        if ($entry.existed) {
            Copy-Item -LiteralPath $entry.backup -Destination $entry.target -Force
        }
        elseif (Test-Path -LiteralPath $entry.target) {
            Remove-Item -LiteralPath $entry.target -Force
        }
    }
}

foreach ($required in @($manager, $configPath) + @($payloads | ForEach-Object { $_.source })) {
    if (-not (Test-Path -LiteralPath $required)) { throw "required deployment input is missing: $required" }
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$listen8768Before = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
if ($serviceBefore.Status -ne 'Running' -or $wsBefore.Status -ne 'Running') {
    throw '8093 and 8768 services must be running before deployment'
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$manifest = @()
$allTargets = @($payloads | ForEach-Object { $_.target }) + @($configPath)
foreach ($target in $allTargets) {
    $relative = $target.Substring($root.Length).TrimStart('\').Replace('\', '__')
    $backup = Join-Path $backupRoot $relative
    $existed = Test-Path -LiteralPath $target
    if ($existed) { Copy-Item -LiteralPath $target -Destination $backup -Force }
    $manifest += [pscustomobject]@{ target = $target; backup = $backup; existed = $existed }
}

$guardPaused = $false
$guardRestored = $false
$deploymentApplied = $false
$rollbackApplied = $false
$postFailure = $null
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    $guardPaused = (Wait-ServiceState -Name $serviceName -DesiredState 'Stopped' -TimeoutSeconds 15).Status -eq 'Stopped'
    [void](Wait-Port -Port 8093 -Listening $false -TimeoutSeconds 15)
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)) { throw '8768 stopped while pausing 8093' }

    foreach ($payload in $payloads) { Install-Payload -Source $payload.source -Target $payload.target }

    $config = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    if (-not $config.env) { Set-ObjectProperty $config 'env' ([pscustomobject]@{}) }
    $reviewEnvironment = [ordered]@{
        BF_DIAGNOSIS_REVIEW_ENABLED = '1'
        BF_DIAGNOSIS_REVIEW_TEST_MODE = '0'
        BF_DIAGNOSIS_AI_ANALYSIS_ENABLED = '1'
        BF_DIAGNOSIS_AI_ANALYSIS_BACKGROUND_ENABLED = '1'
        BF_DIAGNOSIS_AI_ANALYSIS_BUCKET_MINUTES = '5'
        BF_DIAGNOSIS_AI_ANALYSIS_POLL_SECONDS = '30'
        BF_DIAGNOSIS_AI_ANALYSIS_RETRY_SECONDS = '120'
        BF_DIAGNOSIS_AI_ANALYSIS_HISTORY_LIMIT = '12'
        BF_DIAG_REVIEW_REQUIRE_LOGIN = '0'
        BF_DIAG_REVIEW_ANONYMOUS_USERNAME = 'onsite_8093'
        BF_DIAG_REVIEW_ANONYMOUS_ROLE = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('546w5Zy66auY54KJ6ZW/'))
        BF_DIAG_REVIEW_PGHOST = '127.0.0.1'
        BF_DIAG_REVIEW_PGPORT = '5432'
        BF_DIAG_REVIEW_PGDATABASE = 'bf_trend'
        BF_DIAG_REVIEW_PGUSER = 'gl02_sync'
        BF_DIAG_REVIEW_PGPASSWORD_ENV = 'GL02_PGPASSWORD'
        BF_DIAG_REVIEW_PGSCHEMA = 'bf_assistant'
    }
    foreach ($name in $reviewEnvironment.Keys) { Set-ObjectProperty $config.env $name $reviewEnvironment[$name] }
    if ($config.env.PSObject.Properties['BF_DIAG_REVIEW_PGPASSWORD']) {
        $config.env.PSObject.Properties.Remove('BF_DIAG_REVIEW_PGPASSWORD')
    }
    $machineNames = @($config.envMachine | ForEach-Object { [string]$_ })
    foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        if ($machineNames -notcontains $name) { $machineNames += $name }
    }
    Set-ObjectProperty $config 'envMachine' $machineNames
    Write-JsonAtomically -Path $configPath -Value $config
    $deploymentApplied = $true
}
catch {
    if ($deploymentApplied -or $guardPaused) {
        Restore-Deployment -Manifest $manifest
        $rollbackApplied = $true
    }
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    $guardRestored = (Wait-ServiceState -Name $serviceName -DesiredState 'Running' -TimeoutSeconds 25).Status -eq 'Running'
}

$postStage = 'wait-8093-port'
try {
    [void](Wait-Port -Port 8093 -Listening $true -TimeoutSeconds 25)
    $listen8768After = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0]
    $postStage = 'page'
    $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?t=diagnosis-core19-20260806' -TimeoutSec 20
    $postStage = 'diagnosis-context'
    $context = Wait-DiagnosisReviewContext -TimeoutSeconds 90
    $analysisTargetLabel = [string]$context.context.main_label
    if ($analysisTargetLabel -notin @('normal', 'lowline', 'edge', 'center', 'channel', 'cold', 'hot', 'column')) {
        throw "invalid current main label: $analysisTargetLabel"
    }
    $postStage = 'assets'
    $asset = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/assets/bf-diagnosis-review-local.js?t=20260806-core19-r10-foreman-knowledge' -TimeoutSec 20
    $manualAsset = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/assets/bf-diagnosis-manual-score-local.js?t=20260806-core19-r10-foreman-knowledge' -TimeoutSec 20
    $expectedCoreVariableIds = @(
        'P_top_gas_A', 'P_top_gas_B', 'P_top_gas_C', 'P_top_gas_D',
        'T_top_A', 'T_top_B', 'T_top_C', 'T_top_D',
        'P_top', 'T_top', 'Q_blast', 'P_blast_cold', 'P_blast', 'T_blast',
        'PI', 'DP_total', 'DP_upper', 'DP_lower', 'GasUtil'
    )
    $coreEvidenceResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/diagnosis-core-evidence?label=$analysisTargetLabel" -TimeoutSec 30
    $coreEvidence = $coreEvidenceResponse.Content | ConvertFrom-Json
    $coreEndpointIds = @($coreEvidence.evidence.core_variable_evidence | ForEach-Object { [string]$_.id })
    $coreEndpointIdsMatch = ((@($coreEndpointIds | Sort-Object) -join ',') -eq (@($expectedCoreVariableIds | Sort-Object) -join ','))
    $coreEndpointSeriesCount = @($coreEvidence.evidence.core_variable_evidence | Where-Object { @($_.series_60m).Count -gt 0 }).Count
    $protectedHistoryStatus = Get-HttpStatus 'http://127.0.0.1:8093/api/diagnosis-reviews?limit=1'
    $anonymousInvalidScoreStatus = Get-HttpStatus 'http://127.0.0.1:8093/api/diagnosis-manual-scores' 'POST' '{}'
    $listen8768Final = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
    $checks = [ordered]@{
        guard_restored = $guardRestored
        http_8093 = [int]$page.StatusCode
        page_injects_popup = $page.Content.Contains('/assets/bf-diagnosis-review-local.js')
        page_injects_manual_score = $page.Content.Contains('/assets/bf-diagnosis-manual-score-local.js')
        context_enabled = [bool]$context.enabled
        context_can_submit = [bool]$context.auth.can_submit
        context_login_required = [bool]$context.auth.login_required
        context_identity_mode = [string]$context.auth.identity_mode
        review_store_writable = [bool]$context.review_storage.writable
        fixture_disabled = -not [bool]$context.context.fixture_label
        popup_uses_can_submit = $asset.Content.Contains('form.classList.toggle("bfdr-hidden",!canSubmit||reviewed)')
        manual_score_uses_can_submit = $manualAsset.Content.Contains('form.classList.toggle("bfdms-hidden",!canSubmit)')
        manual_score_loads_ai_analysis = $manualAsset.Content.Contains('/api/diagnosis-ai-analysis?')
        manual_score_shows_variable_evidence = $manualAsset.Content.Contains('bfdms-ai-driver-list')
        manual_score_shows_engine_guidance = $manualAsset.Content.Contains('bfdms-ai-action-list')
        manual_score_shows_core_evidence = $manualAsset.Content.Contains('bfdms-core-evidence')
        manual_score_renders_core_chart = $manualAsset.Content.Contains('renderCoreChart')
        manual_score_core_available_while_preparing = $manualAsset.Content.Contains('bfdms-ai-core-early')
        manual_score_retries_transient_analysis_failure = $manualAsset.Content.Contains('renderAi({state:"failed"});state.analysisTimer=setTimeout(loadAiAnalysis,3000)')
        manual_score_loads_lightweight_core_endpoint = $manualAsset.Content.Contains('/api/diagnosis-core-evidence?label=')
        core_endpoint_schema_v1 = [string]$coreEvidence.evidence.schema_version -eq 'diagnosis_core_evidence.v1'
        core_endpoint_count = [int]$coreEvidence.evidence.core_variable_count
        core_endpoint_ids_match = $coreEndpointIdsMatch
        core_endpoint_series_count = $coreEndpointSeriesCount
        ai_analysis_runtime_async = $true
        history_get_still_protected = $protectedHistoryStatus -eq 401
        anonymous_post_reaches_validation = $anonymousInvalidScoreStatus -eq 400
        ws8768_same_pid = [int]$listen8768Before.OwningProcess -eq [int]$listen8768After.OwningProcess
        ws8768_listening_final = $listen8768Final
    }
    $failed = @()
    foreach ($name in @(
        'guard_restored', 'page_injects_popup', 'page_injects_manual_score',
        'context_enabled', 'context_can_submit', 'review_store_writable',
        'fixture_disabled', 'popup_uses_can_submit', 'manual_score_uses_can_submit',
        'manual_score_loads_ai_analysis', 'ai_analysis_runtime_async',
        'manual_score_shows_variable_evidence', 'manual_score_shows_engine_guidance',
        'manual_score_shows_core_evidence', 'manual_score_renders_core_chart',
        'manual_score_core_available_while_preparing',
        'manual_score_retries_transient_analysis_failure',
        'manual_score_loads_lightweight_core_endpoint', 'core_endpoint_schema_v1',
        'core_endpoint_ids_match',
        'history_get_still_protected', 'anonymous_post_reaches_validation',
        'ws8768_same_pid', 'ws8768_listening_final'
    )) {
        if (-not [bool]$checks[$name]) { $failed += "$name=$($checks[$name])" }
    }
    if ([int]$checks.http_8093 -ne 200) { $failed += "http_8093=$($checks.http_8093)" }
    if ([bool]$checks.context_login_required) { $failed += "context_login_required=$($checks.context_login_required)" }
    if ([int]$checks.core_endpoint_count -ne 19) { $failed += "core_endpoint_count=$($checks.core_endpoint_count)" }
    if ([int]$checks.core_endpoint_series_count -ne 19) { $failed += "core_endpoint_series_count=$($checks.core_endpoint_series_count)" }
    if ([string]$checks.context_identity_mode -ne 'onsite_anonymous') { $failed += "context_identity_mode=$($checks.context_identity_mode)" }
    if ($failed.Count -gt 0) { throw "post-deployment verification failed: $($failed -join ', ')" }

    [ordered]@{
        schema = 'ops.8093.diagnosis-core19-trends.guarded-deploy.v3'
        requirement_id = 'REQ-8093-DIAGNOSIS-CORE-19-TRENDS-20260806'
        guard_paused = $guardPaused
        guard_restored = $guardRestored
        rollback_applied = $rollbackApplied
        backup_root = $backupRoot
        checks = $checks
        context = [ordered]@{
            available = [bool]$context.context.available
            abnormal = [bool]$context.context.is_abnormal
            snapshot_source = [string]$context.context.snapshot_source
            candidate_count = @($context.context.candidates).Count
        }
        ai_analysis = [ordered]@{
            verification_mode = 'runtime_async'
            schema_contract = 'diagnosis_ai_analysis.v4'
            target_label = $analysisTargetLabel
            lightweight_core_endpoint_series_count = $coreEndpointSeriesCount
        }
        deployed_files = @($payloads | ForEach-Object {
            [ordered]@{
                relative_path = $_.target.Substring($root.Length).TrimStart('\')
                sha256 = (Get-FileHash -LiteralPath $_.target -Algorithm SHA256).Hash
            }
        })
    } | ConvertTo-Json -Depth 8
}
catch {
    $postFailure = $_
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState 'Stopped' -TimeoutSeconds 15)
    Restore-Deployment -Manifest $manifest
    $rollbackApplied = $true
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState 'Running' -TimeoutSeconds 25)
    [void](Wait-Port -Port 8093 -Listening $true -TimeoutSeconds 25)
    throw "8093 diagnosis AI analysis deployment was rolled back at stage=${postStage}: $($postFailure.Exception.Message)"
}
