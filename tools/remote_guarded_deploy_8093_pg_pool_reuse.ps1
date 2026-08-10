param(
    [string]$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    [string]$PatcherPath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805
$serviceName = "BFV4PreviewProxy8093"
$guardTaskPath = "\BlastFurnaceServices\"
$guardTaskName = "BFV4PreviewProxy8093HealthCheck"
$manager = Join-Path $ProjectRoot "tools\manage_22012_managed_services.ps1"
$configPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$proxyPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$ragPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\bf_knowledge_rag.py"
$python = "C:\Program Files\Python311\python.exe"
$packagePatcher = Join-Path $PSScriptRoot "patch_8093_assistant_pg_pool_reuse.py"
$patcher = if ([string]::IsNullOrWhiteSpace($PatcherPath)) { $packagePatcher } else { $PatcherPath }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $ProjectRoot "logs\deploy_backups\8093_pg_pool_reuse_$stamp"
$expectedConfigHash = "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE"
$expectedProxyHashes = @(
    "8F38DA0286791A95722520D7278AE2A37544E3D4EB255D8A5950FC3CAD50EFD0",
    "B53F01E063138A623B091CB3F36DD72971FF5B844FB2D27C06C222BB417FF5F6"
)
$expectedRagHashes = @(
    "C42CA839CD83541F679D348B6652B0BFFC1AAB2EE72D96C3B08395A70E6289AA",
    "B2CD593A9F9BDC619305AF94FD82600F1547BBE1FE2C145051D09134C907B475"
)
$script:startAttempts = 0

function Get-ListenerRow {
    param([Parameter(Mandatory = $true)][int]$Port)

    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) | Select-Object -First 1
    if ($null -eq $row) {
        throw "TCP $Port is not listening"
    }
    return [ordered]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Wait-ServiceValue {
    param(
        [Parameter(Mandatory = $true)][string]$Desired,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $serviceName -ErrorAction Stop
        if ($service.Status.ToString() -eq $Desired) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$serviceName did not reach $Desired"
}

function Wait-PortValue {
    param(
        [Parameter(Mandatory = $true)][bool]$Listening,
        [int]$TimeoutSeconds = 60
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP 8093 did not reach listening=$Listening"
}

function Start-ManagedServiceWithRetry {
    param([int]$Attempts = 2)

    $lastStartError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $script:startAttempts += 1
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
        try {
            Wait-ServiceValue -Desired "Running" -TimeoutSeconds 45
            Wait-PortValue -Listening $true -TimeoutSeconds 60
            return
        } catch {
            $lastStartError = $_
            if ($attempt -lt $Attempts) {
                Start-Sleep -Seconds 15
            }
        }
    }
    throw $lastStartError
}

function Wait-HttpJson {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 90
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            return Invoke-RestMethod -UseBasicParsing -Uri $Uri -TimeoutSec 20
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "endpoint did not recover: $Uri"
}

foreach ($requiredFile in @($manager, $configPath, $proxyPath, $ragPath, $python, $patcher)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "required file is missing: $requiredFile"
    }
}

$configHashBefore = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
$proxyHashBefore = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
$ragHashBefore = (Get-FileHash -LiteralPath $ragPath -Algorithm SHA256).Hash
if ($configHashBefore -ne $expectedConfigHash) {
    throw "8093 config hash is outside the approved baseline: $configHashBefore"
}
if ($expectedProxyHashes -notcontains $proxyHashBefore) {
    throw "proxy hash is outside the approved baseline: $proxyHashBefore"
}
if ($expectedRagHashes -notcontains $ragHashBefore) {
    throw "RAG hash is outside the approved baseline: $ragHashBefore"
}

& $python $patcher --root $ProjectRoot --check | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "pool reuse patch precheck failed: $LASTEXITCODE"
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne "Running") {
    throw "$serviceName must be Running before deployment"
}
$taskBefore = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
if ($taskBefore.State.ToString() -eq "Disabled") {
    throw "health guard task is disabled before deployment"
}

$listenersBefore = [ordered]@{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) {
    $key = [string]$port
    $listenersBefore[$key] = Get-ListenerRow -Port $port
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item -LiteralPath $proxyPath -Destination (Join-Path $backupRoot "ollama_proxy_server.py")
Copy-Item -LiteralPath $ragPath -Destination (Join-Path $backupRoot "bf_knowledge_rag.py")

$taskPaused = $false
$serviceStopped = $false
$filesChanged = $false
$rollbackApplied = $false
$caught = $null
$patchResult = $null

try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    $taskPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    Wait-ServiceValue -Desired "Stopped"
    Wait-PortValue -Listening $false
    $serviceStopped = $true

    foreach ($port in @(8768, 8094, 8770, 11434)) {
        $key = [string]$port
        $current = Get-ListenerRow -Port $port
        if ($current.pid -ne $listenersBefore[$key].pid) {
            throw "protected listener $port changed while 8093 was stopped"
        }
    }

    $patchJson = & $python $patcher --root $ProjectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "pool reuse patch failed: $LASTEXITCODE"
    }
    $patchResult = $patchJson | ConvertFrom-Json
    $filesChanged = $true

    & $python -m py_compile $proxyPath $ragPath
    if ($LASTEXITCODE -ne 0) {
        throw "patched Python compile failed: $LASTEXITCODE"
    }

    Start-Sleep -Seconds 15
    Start-ManagedServiceWithRetry
    $serviceStopped = $false
} catch {
    $caught = $_
    if ($filesChanged) {
        Copy-Item -LiteralPath (Join-Path $backupRoot "ollama_proxy_server.py") -Destination $proxyPath -Force
        Copy-Item -LiteralPath (Join-Path $backupRoot "bf_knowledge_rag.py") -Destination $ragPath -Force
        $rollbackApplied = $true
    }
} finally {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status.ToString() -ne "Running") {
        try {
            Start-Sleep -Seconds 15
            Start-ManagedServiceWithRetry
        } catch {
            if ($null -eq $caught) { $caught = $_ }
        }
    }
    if ($taskPaused) {
        try {
            Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
        } catch {
            if ($null -eq $caught) { $caught = $_ }
        }
    }
}

if ($null -ne $caught) {
    throw $caught
}

$status = Wait-HttpJson -Uri "http://127.0.0.1:8093/api/ollama/status"
$knowledgeQuestion = [uri]::EscapeDataString("高炉总压差升高时为什么要检查透气性")
$knowledge = Wait-HttpJson -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$knowledgeQuestion&top_k=2"
if (-not $status.ok -or -not $status.model_ok) {
    throw "assistant status did not recover"
}
if (-not $knowledge.enabled -or $knowledge.retrieval_mode -ne "keyword" -or @($knowledge.evidence).Count -lt 1) {
    throw "default keyword knowledge search did not recover"
}

$listenersAfter = [ordered]@{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) {
    $key = [string]$port
    $listenersAfter[$key] = Get-ListenerRow -Port $port
}
if ($listenersAfter["8093"].pid -eq $listenersBefore["8093"].pid) {
    throw "8093 listener PID did not change after backend deployment"
}
foreach ($port in @(8768, 8094, 8770, 11434)) {
    $key = [string]$port
    if ($listenersAfter[$key].pid -ne $listenersBefore[$key].pid) {
        throw "protected listener $port changed during deployment"
    }
}

$taskAfter = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
$result = [ordered]@{
    schema = "ops.8093.assistant-pg-pool-reuse.deploy.v1"
    requirement_id = "ERR-8093-ASSISTANT-PG-POOL-NESTED-LEASE-20260805"
    completed_at = (Get-Date).ToString("o")
    backup_root = $backupRoot
    rollback_applied = $rollbackApplied
    guard_restored = $taskAfter.State.ToString() -ne "Disabled"
    start_attempts = $script:startAttempts
    patch = $patchResult
    hashes = [ordered]@{
        config_before = $configHashBefore
        config_after = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        proxy_before = $proxyHashBefore
        proxy_after = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
        rag_before = $ragHashBefore
        rag_after = (Get-FileHash -LiteralPath $ragPath -Algorithm SHA256).Hash
    }
    listeners_before = @($listenersBefore.Values)
    listeners_after = @($listenersAfter.Values)
    checks = [ordered]@{
        assistant_status_ok = [bool]$status.ok
        model_ok = [bool]$status.model_ok
        knowledge_enabled = [bool]$knowledge.enabled
        retrieval_mode = [string]$knowledge.retrieval_mode
        evidence_count = @($knowledge.evidence).Count
    }
}

$result | ConvertTo-Json -Depth 12
