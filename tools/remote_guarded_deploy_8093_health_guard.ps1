param(
    [string]$GuardSourcePath = "",
    [string]$ConfigPatcherPath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$payloadRoot = "C:\Users\Administrator\AppData\Local\Temp"
$targetScript = Join-Path $root "tools\check_managed_nssm_service_health.ps1"
$configPath = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$temporarySource = Join-Path $payloadRoot "check_managed_nssm_service_health.ps1"
$temporaryPatcher = Join-Path $payloadRoot "patch_8093_health_guard_config.py"
$packageSource = Join-Path $PSScriptRoot "check_managed_nssm_service_health.ps1"
$packagePatcher = Join-Path $PSScriptRoot "patch_8093_health_guard_config.py"
$sourceScript = if (-not [string]::IsNullOrWhiteSpace($GuardSourcePath)) {
    $GuardSourcePath
} elseif (Test-Path -LiteralPath $packageSource -PathType Leaf) {
    $packageSource
} else {
    $temporarySource
}
$configPatcher = if (-not [string]::IsNullOrWhiteSpace($ConfigPatcherPath)) {
    $ConfigPatcherPath
} elseif (Test-Path -LiteralPath $packagePatcher -PathType Leaf) {
    $packagePatcher
} else {
    $temporaryPatcher
}
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"
$statePath = Join-Path $root "logs\proxy_8093.health.state.json"
$healthLogPath = Join-Path $root "logs\proxy_8093.health.log"
$python = "C:\Program Files\Python311\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $root "logs\deploy_backups\8093_health_guard_$stamp"
$expectedScriptHashes = @(
    "F55F5B59BD9155E99C4C89B289A6C1843F640BE82A57235070E1B5148B9E0B95",
    "1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3"
)
$expectedConfigHashes = @(
    "A862003D01553E7EE6413663DA14C651760D9F137AB6C2D7C5CCA4033D14B6FB",
    "D20F01F1E66FF8973AB6720DDEB450AEE50FAE2AC6FFB023E1C04EACA066EACA",
    "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE"
)

function Get-Listener([int]$Port) {
    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)[0]
    if (-not $row) { throw "TCP $Port is not listening" }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Get-HttpHash([string]$Url) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 15
    $bytes = [Text.Encoding]::UTF8.GetBytes($response.Content)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [pscustomobject]@{
            status = [int]$response.StatusCode
            sha256 = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "")
            length = $response.Content.Length
        }
    } finally { $sha.Dispose() }
}

function Install-FileAtomically([string]$Source, [string]$Target) {
    $temporary = "$Target.codex-$stamp.tmp"
    $replaceBackup = "$Target.codex-$stamp.replace.bak"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    try {
        [IO.File]::Replace($temporary, $Target, $replaceBackup, $true)
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
    }
}

function Wait-TaskIdle([int]$TimeoutSeconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
        if ($task.State -ne "Running") { return $task }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$taskPath$taskName did not become idle within ${TimeoutSeconds}s"
}

foreach ($required in @($sourceScript, $configPatcher, $targetScript, $configPath, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file is missing: $required" }
}

$scriptHashBefore = (Get-FileHash -LiteralPath $targetScript -Algorithm SHA256).Hash
$configHashBefore = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
if ($expectedScriptHashes -notcontains $scriptHashBefore) { throw "health script baseline changed: $scriptHashBefore" }
if ($expectedConfigHashes -notcontains $configHashBefore) { throw "8093 config baseline changed: $configHashBefore" }

$taskBefore = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
$taskWasEnabled = $taskBefore.State -ne "Disabled"
$listenersBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersBefore[$port] = Get-Listener $port }
$page8093Before = Get-HttpHash "http://127.0.0.1:8093/?t=health-guard-before-$stamp"
$page8094Before = Get-HttpHash "http://127.0.0.1:8094/?t=health-guard-before-$stamp"
$health8768ScriptPath = Join-Path $root "tools\check_v4_8768_service_health.ps1"
$config11434Path = Join-Path $root "tools\service_configs\22012_BFOllama11434.json"
$protectedHashesBefore = [ordered]@{
    health8768 = (Get-FileHash -LiteralPath $health8768ScriptPath -Algorithm SHA256).Hash
    config11434 = (Get-FileHash -LiteralPath $config11434Path -Algorithm SHA256).Hash
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$scriptBackup = Join-Path $backupRoot "check_managed_nssm_service_health.ps1"
$configBackup = Join-Path $backupRoot "22012_BFV4PreviewProxy8093.json"
Copy-Item -LiteralPath $targetScript -Destination $scriptBackup -Force
Copy-Item -LiteralPath $configPath -Destination $configBackup -Force
$stateExistedBefore = Test-Path -LiteralPath $statePath -PathType Leaf
if ($stateExistedBefore) { Copy-Item -LiteralPath $statePath -Destination (Join-Path $backupRoot "proxy_8093.health.state.json") -Force }

$taskPaused = $false
$taskRestored = $false
$deploymentApplied = $false
$rollbackApplied = $false
try {
    if ($taskWasEnabled) {
        Disable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
        Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
        [void](Wait-TaskIdle 30)
        $taskPaused = $true
    }

    $sourceText = Get-Content -LiteralPath $sourceScript -Raw -Encoding UTF8
    [void][ScriptBlock]::Create($sourceText)
    Install-FileAtomically -Source $sourceScript -Target $targetScript
    & $python -X utf8 $configPatcher --config $configPath
    if ($LASTEXITCODE -ne 0) { throw "health config patch failed with exit $LASTEXITCODE" }

    $targetText = Get-Content -LiteralPath $targetScript -Raw -Encoding UTF8
    [void][ScriptBlock]::Create($targetText)
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $contract = [ordered]@{
        failure_threshold = [int]$config.health.failureThreshold
        service_down_threshold = [int]$config.health.serviceNotRunningFailureThreshold
        pre_restart_backoff_seconds = [int]$config.health.preRestartBackoffSeconds
        restart_cooldown_seconds = [int]$config.health.restartCooldownSeconds
    }
    if ($contract.failure_threshold -ne 3 -or $contract.service_down_threshold -ne 1 -or
        $contract.pre_restart_backoff_seconds -ne 15 -or $contract.restart_cooldown_seconds -ne 600) {
        throw "8093 health contract verification failed: $($contract | ConvertTo-Json -Compress)"
    }
    $deploymentApplied = $true
}
catch {
    Copy-Item -LiteralPath $scriptBackup -Destination $targetScript -Force
    Copy-Item -LiteralPath $configBackup -Destination $configPath -Force
    if ($stateExistedBefore) {
        Copy-Item -LiteralPath (Join-Path $backupRoot "proxy_8093.health.state.json") -Destination $statePath -Force
    } else {
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }
    $rollbackApplied = $true
    throw
}
finally {
    if ($taskWasEnabled) {
        Enable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
        $taskRestored = (Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath).State -ne "Disabled"
    } else { $taskRestored = $true }
}

try {
    Start-ScheduledTask -TaskName $taskName -TaskPath $taskPath
    [void](Wait-TaskIdle 60)
    $taskInfoAfter = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
    if ($taskInfoAfter.LastTaskResult -ne 0) { throw "health task result is $($taskInfoAfter.LastTaskResult)" }

    $listenersAfter = @{}
    foreach ($port in @(8093, 8768, 8094, 8770, 11434)) { $listenersAfter[$port] = Get-Listener $port }
    $page8093After = Get-HttpHash "http://127.0.0.1:8093/?t=health-guard-after-$stamp"
    $page8094After = Get-HttpHash "http://127.0.0.1:8094/?t=health-guard-after-$stamp"
    $ollamaStatus = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/ollama/status" -TimeoutSec 15).Content | ConvertFrom-Json
    $loadedModels = ((Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 15).Content | ConvertFrom-Json).models
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $protectedHashesAfter = [ordered]@{
        health8768 = (Get-FileHash -LiteralPath $health8768ScriptPath -Algorithm SHA256).Hash
        config11434 = (Get-FileHash -LiteralPath $config11434Path -Algorithm SHA256).Hash
    }

    $checks = [ordered]@{
        task_paused = $taskPaused
        task_restored = $taskRestored
        task_result_zero = $taskInfoAfter.LastTaskResult -eq 0
        service_8093_pid_unchanged = $listenersBefore[8093].pid -eq $listenersAfter[8093].pid
        ws_8768_pid_unchanged = $listenersBefore[8768].pid -eq $listenersAfter[8768].pid
        preview_8094_pid_unchanged = $listenersBefore[8094].pid -eq $listenersAfter[8094].pid
        db_bridge_8770_pid_unchanged = $listenersBefore[8770].pid -eq $listenersAfter[8770].pid
        ollama_11434_pid_unchanged = $listenersBefore[11434].pid -eq $listenersAfter[11434].pid
        page_8093_unchanged = $page8093Before.sha256 -eq $page8093After.sha256
        page_8094_unchanged = $page8094Before.sha256 -eq $page8094After.sha256
        health_8768_script_unchanged = $protectedHashesBefore.health8768 -eq $protectedHashesAfter.health8768
        config_11434_unchanged = $protectedHashesBefore.config11434 -eq $protectedHashesAfter.config11434
        ollama_status_ok = [bool]$ollamaStatus.ok -and [bool]$ollamaStatus.model_ok
        only_approved_27b_loaded = @($loadedModels).Count -eq 1 -and [string]$loadedModels[0].name -eq "chiqiong-blast-furnace:latest"
        state_reset = [int]$state.consecutiveFailures -eq 0
    }
    $failed = @($checks.Keys | Where-Object { -not [bool]$checks[$_] })
    if ($failed.Count -gt 0) { throw "post-deploy checks failed: $($failed -join ', ')" }

    [ordered]@{
        schema = "ops.8093.health-guard.guarded-deploy.v1"
        requirement_id = "OPS-8093-ASSISTANT-HEALTH-GUARD-FIX-20260804"
        deployed_at = (Get-Date).ToString("o")
        backup_root = $backupRoot
        rollback_applied = $rollbackApplied
        script = [ordered]@{
            before_sha256 = $scriptHashBefore
            after_sha256 = (Get-FileHash -LiteralPath $targetScript -Algorithm SHA256).Hash
        }
        config = [ordered]@{
            before_sha256 = $configHashBefore
            after_sha256 = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
            contract = $contract
        }
        state = $state
        checks = $checks
        health_log_tail = @(Get-Content -LiteralPath $healthLogPath -Tail 12 -Encoding UTF8 | ForEach-Object { [string]$_ })
    } | ConvertTo-Json -Depth 10
}
catch {
    if ($deploymentApplied) {
        Disable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
        Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
        [void](Wait-TaskIdle 30)
        Copy-Item -LiteralPath $scriptBackup -Destination $targetScript -Force
        Copy-Item -LiteralPath $configBackup -Destination $configPath -Force
        if ($stateExistedBefore) {
            Copy-Item -LiteralPath (Join-Path $backupRoot "proxy_8093.health.state.json") -Destination $statePath -Force
        } else {
            Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        }
        Enable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
        $rollbackApplied = $true
    }
    throw "8093 health-guard deployment rolled back: $($_.Exception.Message)"
}
