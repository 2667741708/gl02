param(
    [string]$PatcherPath = "",
    [string]$SimulationInputPath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if (-not [string]::IsNullOrWhiteSpace($SimulationInputPath)) {
    $simulation = Get-Content -LiteralPath $SimulationInputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pidRows = @(
        foreach ($property in $simulation.listeners.PSObject.Properties) {
            [ordered]@{
                port = [int]$property.Name
                before = [int]$property.Value.before
                after = [int]$property.Value.after
            }
        }
    )
    [ordered]@{
        schema = "ops.8093.knowledge-keyword.guarded-deploy.simulation.v1"
        rollback_applied = [bool]$simulation.rollback_applied
        pids = $pidRows
        checks = [ordered]@{
            process_mode_keyword = [bool]$simulation.process_mode_keyword
            default_keyword_search_ok = [bool]$simulation.default_keyword_search_ok
        }
    } | ConvertTo-Json -Depth 10
    exit 0
}

# OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$serviceName = "BFV4PreviewProxy8093"
$manager = Join-Path $root "tools\manage_22012_managed_services.ps1"
$configPath = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$guardScript = Join-Path $root "tools\check_managed_nssm_service_health.ps1"
$health8768Script = Join-Path $root "tools\check_v4_8768_service_health.ps1"
$ollamaConfig = Join-Path $root "tools\service_configs\22012_BFOllama11434.json"
$preview8094Runner = Join-Path $root "tools\run_22012_8094_preview.ps1"
$backend = Join-Path $root "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$ragBackend = Join-Path $root "高炉前端数据\智能助手\backend\bf_knowledge_rag.py"
$payloadRoot = "C:\Users\Administrator\AppData\Local\Temp"
$temporaryPatcher = Join-Path $payloadRoot "patch_8093_keyword_knowledge_mode.py"
$packagePatcher = Join-Path $PSScriptRoot "patch_8093_keyword_knowledge_mode.py"
$patcher = if (-not [string]::IsNullOrWhiteSpace($PatcherPath)) {
    $PatcherPath
} elseif (Test-Path -LiteralPath $packagePatcher -PathType Leaf) {
    $packagePatcher
} else {
    $temporaryPatcher
}
$python = "C:\Program Files\Python311\python.exe"
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"
$statePath = Join-Path $root "logs\proxy_8093.health.state.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $root "logs\deploy_backups\8093_knowledge_keyword_$stamp"
$expectedConfigHashes = @(
    "D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA",
    "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE"
)
$expectedGuardHash = "1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3"
$expectedBackendHash = "B4DFBDF15BD7C1D2D731BEB2A45238C881FEC75B71F2304D619DEF3D2F2C812A"
$expectedRagHash = "C42CA839CD83541F679D348B6652B0BFFC1AAB2EE72D96C3B08395A70E6289AA"

function Get-Listener([int]$Port) {
    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)[0]
    if (-not $row) { throw "TCP $Port is not listening" }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Wait-ServiceState([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 30) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 30) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening within ${TimeoutSeconds}s"
}

function Wait-TaskIdle([int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
        if ($task.State.ToString() -ne "Running") { return $task }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$taskPath$taskName did not become idle within ${TimeoutSeconds}s"
}

function Get-HttpHash([string]$Uri) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 15
    $bytes = [Text.Encoding]::UTF8.GetBytes($response.Content)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [ordered]@{
            status = [int]$response.StatusCode
            sha256 = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "")
            length = $response.Content.Length
        }
    } finally { $sha.Dispose() }
}

function Get-ProcessEnvironmentValue([int]$TargetProcessId, [string]$Name) {
    $code = @"
import sys
import psutil
print(psutil.Process(int(sys.argv[1])).environ().get(sys.argv[2], ""))
"@
    $temporary = Join-Path $env:TEMP ("bf_keyword_env_" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($temporary, $code, [Text.UTF8Encoding]::new($false))
    try {
        return (& $python $temporary $TargetProcessId $Name 2>$null) -join "`n"
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Assert-HealthContract($Config) {
    $contract = [ordered]@{
        failure_threshold = [int]$Config.health.failureThreshold
        service_down_threshold = [int]$Config.health.serviceNotRunningFailureThreshold
        pre_restart_backoff_seconds = [int]$Config.health.preRestartBackoffSeconds
        restart_cooldown_seconds = [int]$Config.health.restartCooldownSeconds
    }
    if ($contract.failure_threshold -ne 3 -or $contract.service_down_threshold -ne 1 -or
        $contract.pre_restart_backoff_seconds -ne 15 -or $contract.restart_cooldown_seconds -ne 600) {
        throw "8093 health contract drifted: $($contract | ConvertTo-Json -Compress)"
    }
    return $contract
}

foreach ($required in @(
    $manager, $configPath, $guardScript, $health8768Script, $ollamaConfig,
    $preview8094Runner, $backend, $ragBackend, $patcher, $python
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file is missing: $required" }
}

$configHashBefore = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
if ($expectedConfigHashes -notcontains $configHashBefore) { throw "8093 config baseline changed: $configHashBefore" }
if ((Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash -ne $expectedGuardHash) { throw "8093 guard baseline changed" }
if ((Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash -ne $expectedBackendHash) { throw "8093 backend baseline changed" }
if ((Get-FileHash -LiteralPath $ragBackend -Algorithm SHA256).Hash -ne $expectedRagHash) { throw "RAG backend baseline changed" }

$configBefore = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$healthContractBefore = Assert-HealthContract $configBefore
if ([string]$configBefore.serviceName -ne $serviceName) { throw "unexpected 8093 service config" }
$modeBefore = [string]$configBefore.env.BF_QA_KNOWLEDGE_SEARCH_MODE
if (-not [string]::IsNullOrWhiteSpace($modeBefore) -and $modeBefore.Trim().ToLowerInvariant() -notin @("hybrid", "keyword")) {
    throw "unexpected knowledge mode before deployment: $modeBefore"
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne "Running") { throw "$serviceName must be Running before deployment" }
$taskBefore = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
if ($taskBefore.State.ToString() -eq "Disabled") { throw "$taskPath$taskName is disabled before deployment" }
$taskWasEnabled = $true

$listenersBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersBefore[$port] = Get-Listener $port }
$page8093Before = Get-HttpHash "http://127.0.0.1:8093/?t=knowledge-keyword-before-$stamp"
$page8094Before = Get-HttpHash "http://127.0.0.1:8094/?t=knowledge-keyword-before-$stamp"
$protectedHashesBefore = [ordered]@{
    guard = (Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash
    health8768 = (Get-FileHash -LiteralPath $health8768Script -Algorithm SHA256).Hash
    ollama_config = (Get-FileHash -LiteralPath $ollamaConfig -Algorithm SHA256).Hash
    preview8094_runner = (Get-FileHash -LiteralPath $preview8094Runner -Algorithm SHA256).Hash
    backend = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
    rag_backend = (Get-FileHash -LiteralPath $ragBackend -Algorithm SHA256).Hash
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$configBackup = Join-Path $backupRoot "22012_BFV4PreviewProxy8093.json"
Copy-Item -LiteralPath $configPath -Destination $configBackup -Force

$taskPaused = $false
$taskRestored = $false
$serviceStopped = $false
$serviceStarted = $false
$rollbackApplied = $false
$patchReport = $null
try {
    Disable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
    Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    [void](Wait-TaskIdle 45)
    $taskPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState "Stopped" -TimeoutSeconds 30)
    Wait-Port -Port 8093 -Listening $false -TimeoutSeconds 30
    $serviceStopped = $true
    foreach ($port in @(8768, 8094, 8770, 11434)) {
        if ((Get-Listener $port).pid -ne $listenersBefore[$port].pid) { throw "protected port $port changed while 8093 was stopped" }
    }

    $patchOutput = & $python -X utf8 $patcher --config $configPath 2>&1
    if ($LASTEXITCODE -ne 0) { throw "keyword config patch failed: $($patchOutput -join ' ')" }
    $patchReport = (($patchOutput | ForEach-Object { [string]$_ }) -join "`n") | ConvertFrom-Json
    $configAfterPatch = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $healthContractAfter = Assert-HealthContract $configAfterPatch
    if ([string]$configAfterPatch.env.BF_QA_KNOWLEDGE_SEARCH_MODE -ne "keyword") {
        throw "keyword mode was not written to the 8093 config"
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState -Name $serviceName -DesiredState "Running" -TimeoutSeconds 45)
    Wait-Port -Port 8093 -Listening $true -TimeoutSeconds 45
    $serviceStarted = $true

    Enable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
    $taskRestored = (Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath).State.ToString() -ne "Disabled"
    Start-ScheduledTask -TaskName $taskName -TaskPath $taskPath
    [void](Wait-TaskIdle 75)
    $taskInfoAfter = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
    if ($taskInfoAfter.LastTaskResult -ne 0) { throw "health task result is $($taskInfoAfter.LastTaskResult)" }

    $listenersAfter = @{}
    foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersAfter[$port] = Get-Listener $port }
    $page8093After = Get-HttpHash "http://127.0.0.1:8093/?t=knowledge-keyword-after-$stamp"
    $page8094After = Get-HttpHash "http://127.0.0.1:8094/?t=knowledge-keyword-after-$stamp"
    $status = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8093/api/ollama/status" -TimeoutSec 20
    $processes = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 20
    $probeQuestion = [uri]::EscapeDataString("高炉总压差升高时为什么要检查透气性")
    $knowledge = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$probeQuestion&top_k=2" -TimeoutSec 30
    $runtimeMode = Get-ProcessEnvironmentValue -TargetProcessId $listenersAfter[8093].pid -Name "BF_QA_KNOWLEDGE_SEARCH_MODE"
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $protectedHashesAfter = [ordered]@{
        guard = (Get-FileHash -LiteralPath $guardScript -Algorithm SHA256).Hash
        health8768 = (Get-FileHash -LiteralPath $health8768Script -Algorithm SHA256).Hash
        ollama_config = (Get-FileHash -LiteralPath $ollamaConfig -Algorithm SHA256).Hash
        preview8094_runner = (Get-FileHash -LiteralPath $preview8094Runner -Algorithm SHA256).Hash
        backend = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
        rag_backend = (Get-FileHash -LiteralPath $ragBackend -Algorithm SHA256).Hash
    }
    $loadedModels = @($processes.models)
    $checks = [ordered]@{
        task_paused = $taskPaused
        task_restored = $taskRestored
        task_result_zero = $taskInfoAfter.LastTaskResult -eq 0
        service_stopped = $serviceStopped
        service_started = $serviceStarted
        service_8093_pid_changed = $listenersBefore[8093].pid -ne $listenersAfter[8093].pid
        ws_8768_pid_unchanged = $listenersBefore[8768].pid -eq $listenersAfter[8768].pid
        preview_8094_pid_unchanged = $listenersBefore[8094].pid -eq $listenersAfter[8094].pid
        db_bridge_8770_pid_unchanged = $listenersBefore[8770].pid -eq $listenersAfter[8770].pid
        ollama_11434_pid_unchanged = $listenersBefore[11434].pid -eq $listenersAfter[11434].pid
        page_8093_unchanged = $page8093Before.sha256 -eq $page8093After.sha256
        page_8094_unchanged = $page8094Before.sha256 -eq $page8094After.sha256
        protected_hashes_unchanged = (@($protectedHashesBefore.Keys | Where-Object { $protectedHashesBefore[$_] -ne $protectedHashesAfter[$_] }).Count -eq 0)
        config_mode_keyword = [string]$configAfterPatch.env.BF_QA_KNOWLEDGE_SEARCH_MODE -eq "keyword"
        process_mode_keyword = $runtimeMode.Trim().ToLowerInvariant() -eq "keyword"
        knowledge_search_mode_keyword = [string]$knowledge.retrieval_mode -eq "keyword"
        default_keyword_search_ok = [bool]$knowledge.ok -and [bool]$knowledge.enabled -and [string]$knowledge.retrieval_mode -eq "keyword" -and @($knowledge.evidence).Count -gt 0
        ollama_status_ok = [bool]$status.ok -and [bool]$status.proxy_ok -and [bool]$status.model_ok
        only_approved_27b_loaded = $loadedModels.Count -eq 1 -and [string]$loadedModels[0].name -eq "chiqiong-blast-furnace:latest"
        health_contract_preserved = ($healthContractBefore | ConvertTo-Json -Compress) -eq ($healthContractAfter | ConvertTo-Json -Compress)
        health_state_clear = [int]$state.consecutiveFailures -eq 0
    }
    $failed = @($checks.Keys | Where-Object { -not [bool]$checks[$_] })
    if ($failed.Count -gt 0) { throw "post-deployment checks failed: $($failed -join ', ')" }

    [ordered]@{
        schema = "ops.8093.knowledge-keyword.guarded-deploy.v1"
        requirement_id = "OPS-8093-KNOWLEDGE-KEYWORD-MODE-20260805"
        deployed_at = (Get-Date).ToString("o")
        backup_root = $backupRoot
        rollback_applied = $rollbackApplied
        config = [ordered]@{
            before_sha256 = $configHashBefore
            after_sha256 = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
            mode_before = $modeBefore
            mode_after = [string]$configAfterPatch.env.BF_QA_KNOWLEDGE_SEARCH_MODE
            patch_changed = [bool]$patchReport.changed
            health_contract = $healthContractAfter
        }
        pids = @(
            foreach ($port in @(8093, 8768, 8094, 8770, 11434)) {
                [ordered]@{
                    port = $port
                    before = $listenersBefore[$port].pid
                    after = $listenersAfter[$port].pid
                }
            }
        )
        knowledge = [ordered]@{
            knowledge_search_mode = "keyword"
            retrieval_mode = [string]$knowledge.retrieval_mode
            evidence_count = @($knowledge.evidence).Count
            titles = @($knowledge.evidence | ForEach-Object { [string]$_.title })
        }
        loaded_models = @($loadedModels | ForEach-Object { [string]$_.name })
        checks = $checks
    } | ConvertTo-Json -Depth 10
}
catch {
    $failure = $_
    try {
        Disable-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue | Out-Null
        Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
        [void](Wait-TaskIdle 45)
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
        [void](Wait-ServiceState -Name $serviceName -DesiredState "Stopped" -TimeoutSeconds 30)
        Copy-Item -LiteralPath $configBackup -Destination $configPath -Force
        $rollbackApplied = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
        [void](Wait-ServiceState -Name $serviceName -DesiredState "Running" -TimeoutSeconds 45)
        Wait-Port -Port 8093 -Listening $true -TimeoutSeconds 45
    } finally {
        if ($taskWasEnabled) {
            Enable-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue | Out-Null
            $taskRestored = (Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath).State.ToString() -ne "Disabled"
        }
    }
    throw "8093 keyword deployment rolled back=$rollbackApplied task_restored=${taskRestored}: $($failure.Exception.Message)"
}
