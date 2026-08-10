param(
    [string]$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# ERR-8093-ASSISTANT-SERVICE-UNAVAILABLE-20260806
$serviceName = "BFV4PreviewProxy8093"
$guardTaskPath = "\BlastFurnaceServices\"
$guardTaskName = "BFV4PreviewProxy8093HealthCheck"
$manager = Join-Path $ProjectRoot "tools\manage_22012_managed_services.ps1"
$configPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$guardPath = Join-Path $ProjectRoot "tools\check_managed_nssm_service_health.ps1"
$proxyPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$ragPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\bf_knowledge_rag.py"
$assistantPgPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\assistant_pg.py"
$statePath = Join-Path $ProjectRoot "logs\proxy_8093.health.state.json"
$expectedHashes = [ordered]@{
    guard = "1A4B2C56D5E86BC6DCC7D82700142BF40B936492712A20AD34997953DCD9C2B3"
    rag = "B2CD593A9F9BDC619305AF94FD82600F1547BBE1FE2C145051D09134C907B475"
    assistant_pg = "91D345B1F121CEA407EE5429597CE0A0C6055749F2DAA8F2D9A7C31065CDBF5B"
}
$expectedRuntimePairs = @(
    "8A24C83DF93008DD8E358682558E8755442D87052A09FB24F39778F2EAF51FDE:979587B4C011FD893D7F737BBF5727F2A82123F25E8DA12CEC5BFD45778E6FED",
    "7541DB038ADD3CAB3F7DBDC6205117D049F4C440C636037EE92A5CC0E9517C5B:381516CB59B1C005844E3D1D322C96820194045B04D3AC1F35D71BDB88629509",
    "7541DB038ADD3CAB3F7DBDC6205117D049F4C440C636037EE92A5CC0E9517C5B:623FF462A8E688FC40DA301B46A7818E287F095C62419999F08450A3554DFBBB"
)
$targetPorts = @(5432, 8093, 8094, 8768, 8770, 11434)
$protectedPorts = @(5432, 8094, 8768, 8770, 11434)
$script:startAttempts = 0
$deploymentMutex = [Threading.Mutex]::new($false, "Global\BFV4PreviewProxy8093Deployment")
$deploymentLockTaken = $false

function Get-ListenerSnapshot {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $targetPorts -contains [int]$_.LocalPort })
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

function Test-LocalTcpPort {
    param([Parameter(Mandatory = $true)][int]$Port)

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(500) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-ServiceAndPort {
    param(
        [Parameter(Mandatory = $true)][string]$DesiredService,
        [Parameter(Mandatory = $true)][bool]$DesiredListener,
        [int]$TimeoutSeconds = 75
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $serviceName -ErrorAction Stop
        $serviceReady = $service.Status.ToString() -eq $DesiredService
        $listenerReady = (Test-LocalTcpPort -Port 8093) -eq $DesiredListener
        if ($serviceReady -and $listenerReady) { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$serviceName did not reach service=$DesiredService listener=$DesiredListener"
}

function Wait-AssistantStatus {
    param([int]$TimeoutSeconds = 90)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $status = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:8093/api/ollama/status" -TimeoutSec 10
            if ($status.ok -and $status.model_ok) { return $status }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "8093 assistant status did not recover"
}

function Start-ManagedServiceWithRetry {
    param([int]$Attempts = 2)

    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $script:startAttempts += 1
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
        } catch {
            $lastError = $_
        }
        try {
            Wait-ServiceAndPort -DesiredService "Running" -DesiredListener $true
            return
        } catch {
            $lastError = $_
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds 15 }
    }
    throw $lastError
}

function Wait-GuardIdle {
    param([int]$TimeoutSeconds = 60)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
        if ($task.State.ToString() -ne "Running") { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "health guard did not finish its verification run"
}

try {
$deploymentLockTaken = $deploymentMutex.WaitOne([TimeSpan]::FromMinutes(2))
if (-not $deploymentLockTaken) { throw "another 8093 deployment owns the global deployment lock" }

foreach ($path in @($manager, $configPath, $guardPath, $proxyPath, $ragPath, $assistantPgPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "required file is missing: $path" }
}

$actualHashes = [ordered]@{
    config = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
    guard = (Get-FileHash -LiteralPath $guardPath -Algorithm SHA256).Hash
    proxy = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
    rag = (Get-FileHash -LiteralPath $ragPath -Algorithm SHA256).Hash
    assistant_pg = (Get-FileHash -LiteralPath $assistantPgPath -Algorithm SHA256).Hash
}
foreach ($name in $expectedHashes.Keys) {
    if ($actualHashes[$name] -ne $expectedHashes[$name]) {
        throw "$name hash is outside the approved recovered baseline: $($actualHashes[$name])"
    }
}
$runtimePair = "$($actualHashes.config):$($actualHashes.proxy)"
if ($expectedRuntimePairs -notcontains $runtimePair) {
    throw "config/proxy hashes are not an approved runtime pair: $runtimePair"
}

$guardBefore = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
if ($guardBefore.State.ToString() -eq "Disabled") { throw "health guard task is disabled" }
foreach ($dependency in @("BFOllama11434", "BFV4PreviewWs8768")) {
    $service = Get-Service -Name $dependency -ErrorAction Stop
    if ($service.Status.ToString() -ne "Running") { throw "protected service is not running: $dependency" }
}

$snapshotBefore = Get-ListenerSnapshot
$listenersBefore = [ordered]@{}
foreach ($port in $targetPorts) {
    $listenersBefore[[string]$port] = Get-ListenerRow -Port $port -Snapshot $snapshotBefore
}
foreach ($port in $protectedPorts) {
    if (-not $listenersBefore[[string]$port].listening) { throw "protected listener is missing: $port" }
}

$guardPaused = $false
$caught = $null
try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    $guardPaused = $true

    $serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
    if ($serviceBefore.Status.ToString() -ne "Stopped" -or $listenersBefore["8093"].listening) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
        Wait-ServiceAndPort -DesiredService "Stopped" -DesiredListener $false
    }

    Start-Sleep -Seconds 15
    Start-ManagedServiceWithRetry
} catch {
    $caught = $_
} finally {
    if ($guardPaused) {
        try {
            Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
        } catch {
            if ($null -eq $caught) { $caught = $_ }
        }
    }
}
if ($null -ne $caught) { throw $caught }

$status = Wait-AssistantStatus
$knowledgeQuestion = [uri]::EscapeDataString("高炉总压差升高时为什么要检查透气性")
$knowledge = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$knowledgeQuestion&top_k=2" -TimeoutSec 30
if (-not $knowledge.enabled -or $knowledge.retrieval_mode -ne "keyword" -or @($knowledge.evidence).Count -lt 1) {
    throw "default keyword knowledge search did not recover"
}

$snapshotAfter = Get-ListenerSnapshot
$listenersAfter = [ordered]@{}
foreach ($port in $targetPorts) {
    $listenersAfter[[string]$port] = Get-ListenerRow -Port $port -Snapshot $snapshotAfter
}
foreach ($port in $protectedPorts) {
    if ($listenersAfter[[string]$port].pid -ne $listenersBefore[[string]$port].pid) {
        throw "protected listener changed during 8093 service recovery: $port"
    }
}

$pidBeforeGuardCheck = $listenersAfter["8093"].pid
Start-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath
Wait-GuardIdle
$snapshotAfterGuard = Get-ListenerSnapshot
$listenerAfterGuard = Get-ListenerRow -Port 8093 -Snapshot $snapshotAfterGuard
if (-not $listenerAfterGuard.listening -or $listenerAfterGuard.pid -ne $pidBeforeGuardCheck) {
    throw "health guard changed the recovered 8093 process"
}

$guardState = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) {
    $guardState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
}
if ($null -eq $guardState -or [int]$guardState.consecutiveFailures -ne 0) {
    throw "health guard failure state was not cleared"
}

$result = [ordered]@{
    schema = "ops.8093.assistant-service-recovery.v1"
    requirement_id = "ERR-8093-ASSISTANT-SERVICE-UNAVAILABLE-20260806"
    completed_at = (Get-Date).ToString("o")
    guard_restored = (Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath).State.ToString() -ne "Disabled"
    start_attempts = $script:startAttempts
    hashes = $actualHashes
    listeners_before = @($listenersBefore.Values)
    listeners_after = @($listenersAfter.Values)
    guard_state = $guardState
    checks = [ordered]@{
        assistant_status_ok = [bool]$status.ok
        model_ok = [bool]$status.model_ok
        knowledge_enabled = [bool]$knowledge.enabled
        retrieval_mode = [string]$knowledge.retrieval_mode
        evidence_count = @($knowledge.evidence).Count
        guard_pid_stable = $listenerAfterGuard.pid -eq $pidBeforeGuardCheck
    }
}
$result | ConvertTo-Json -Depth 12
} finally {
    if ($deploymentLockTaken) { $deploymentMutex.ReleaseMutex() }
    $deploymentMutex.Dispose()
}
