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
$backupRoot = Join-Path $root "logs\deploy_backups\8093_ai_data_limit_fix_$stamp"

$payloads = @(
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_review.py'
        source = Join-Path $payloadRoot 'diagnosis_review.py'
    }
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\diag_ai_evidence.py'
        source = Join-Path $payloadRoot 'diag_ai_evidence.py'
    }
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_model_review.py'
        source = Join-Path $payloadRoot 'diagnosis_model_review.py'
    }
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\diagnosis_ai_analysis_api.py'
        source = Join-Path $payloadRoot 'diagnosis_ai_analysis_api.py'
    }
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\bf_knowledge_rag.py'
        source = Join-Path $payloadRoot 'bf_knowledge_rag.py'
    }
    [pscustomobject]@{
        target = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
        source = Join-Path $payloadRoot 'ollama_proxy_server.py'
    }
)

function Wait-ServiceState {
    param([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 25)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
}

function Wait-Port {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 25)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return $present }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening within ${TimeoutSeconds}s"
}

function Install-Payload([string]$Source, [string]$Target) {
    $temporary = "$Target.codex-$stamp.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Restore-Deployment([array]$Manifest) {
    foreach ($entry in $Manifest) {
        Copy-Item -LiteralPath $entry.backup -Destination $entry.target -Force
    }
}

foreach ($required in @($manager, $configPath) + @($payloads | ForEach-Object { $_.source })) {
    if (-not (Test-Path -LiteralPath $required)) { throw "required deployment input is missing: $required" }
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
if ($serviceBefore.Status -ne 'Running' -or $wsBefore.Status -ne 'Running') {
    throw '8093 and 8768 services must be running before deployment'
}
[void](Wait-Port -Port 8093 -Listening $true)
[void](Wait-Port -Port 8768 -Listening $true)
$wsPidBefore = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0].OwningProcess

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$manifest = @()
foreach ($payload in $payloads) {
    $backup = Join-Path $backupRoot ([IO.Path]::GetFileName($payload.target))
    Copy-Item -LiteralPath $payload.target -Destination $backup -Force
    $manifest += [pscustomobject]@{ target = $payload.target; backup = $backup }
}

$guardPaused = $false
$guardRestored = $false
$rollbackApplied = $false
$deploymentApplied = $false
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState 'Stopped')
    $guardPaused = $true
    [void](Wait-Port -Port 8093 -Listening $false)
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)) {
        throw '8768 stopped while pausing 8093'
    }
    foreach ($payload in $payloads) {
        Install-Payload -Source $payload.source -Target $payload.target
    }
    $deploymentApplied = $true
}
catch {
    if ($guardPaused) {
        Restore-Deployment -Manifest $manifest
        $rollbackApplied = $true
    }
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState 'Running')
    [void](Wait-Port -Port 8093 -Listening $true)
    $guardRestored = $true
}

$page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?t=ai-data-limit-fix-20260808' -TimeoutSec 20
$analysisResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=cold&t=ai-data-limit-fix-20260808' -TimeoutSec 40
$analysis = $analysisResponse.Content | ConvertFrom-Json
$record = $analysis.analysis
$wsPidAfter = @(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop)[0].OwningProcess
$analysisItems = @()
if ($record -and $record.PSObject.Properties['analysis']) { $analysisItems = @($record.analysis) }
if ($analysisItems.Count -eq 0 -and $record -and $record.PSObject.Properties['analyses']) { $analysisItems = @($record.analyses) }
$dataLimits = @($analysisItems | ForEach-Object {
    if ($_.data_limits) { $_.data_limits | ForEach-Object { [string]$_ } }
})
$badLimit = @($dataLimits | Where-Object { $_ -match 'L_north|L_south|T_top_[A-D]|北料线|南料线|顶温' })
$checks = [ordered]@{
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    rollback_applied = $rollbackApplied
    deployment_applied = $deploymentApplied
    http_8093 = [int]$page.StatusCode
    response_ok = [bool]$analysis.ok
    response_status = [int]$analysisResponse.StatusCode
    analysis_state = [string]$record.state
    analysis_ready = ([string]$record.state -in @('preparing', 'reasoning', 'completed', 'failed'))
    data_limits_count = $dataLimits.Count
    no_false_sensor_limits = ($badLimit.Count -eq 0)
    ws8768_same_pid = ([int]$wsPidBefore -eq [int]$wsPidAfter)
    ws8768_listening = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
}
$failed = @($checks.Keys | Where-Object { $_ -notin @('data_limits_count', 'rollback_applied') -and -not [bool]$checks[$_] })
if ($checks.http_8093 -ne 200) { $failed += 'http_8093' }
if ($failed.Count -gt 0) {
    throw "post-deployment verification failed: $($failed -join ', '); data_limits=$($dataLimits -join ' | ')"
}

[ordered]@{
    schema = 'ops.8093.ai-data-limit-fix.guarded-deploy.v2'
    requirement_id = 'BUG-8093-DIAGNOSIS-AI-FALSE-DATA-LIMITS-20260808'
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    rollback_applied = $rollbackApplied
    backup_root = $backupRoot
    checks = $checks
    data_limits = $dataLimits
    deployed_files = @($payloads | ForEach-Object {
        [ordered]@{
            relative_path = $_.target.Substring($root.Length).TrimStart('\')
            sha256 = (Get-FileHash -LiteralPath $_.target -Algorithm SHA256).Hash
        }
    })
} | ConvertTo-Json -Depth 8
