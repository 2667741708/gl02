$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$guardTaskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$python = 'C:\Program Files\Python311\python.exe'
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_heat_chemistry_stage'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\8093_heat_chemistry_$stamp"

$files = @(
    @{ Relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'; Stage = 'ollama_proxy_server.py'; Hash = '381516CB59B1C005844E3D1D322C96820194045B04D3AC1F35D71BDB88629509' },
    @{ Relative = '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'; Stage = 'imes_relay_mcp_server.py'; Hash = 'ACCD9588DF61C9BDCA003E4DA6D93ABEB051ECBF49CCE5123F392CE0D410E7DC' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\heat_analysis.json'; Stage = 'heat_analysis.json'; Hash = '29AF8843176CD6FA1B4EB0C8B2ABE50C6F6009F94D3D3D35C7BE1372E1005BA8' }
)

function Get-Listener([int]$Port, [bool]$Required = $true) {
    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)[0]
    if (-not $row) {
        if ($Required) { throw "TCP $Port is not listening" }
        return $null
    }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Wait-ServiceState([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening"
}

function Wait-GuardTaskIdle([int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
        if ($task.State.ToString() -ne 'Running') { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw '8093 health task did not become idle'
}

foreach ($required in @($manager, $configPath, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "missing required file: $required" }
}
foreach ($item in $files) {
    $stage = Join-Path $stageRoot $item.Stage
    if (-not (Test-Path -LiteralPath $stage -PathType Leaf)) { throw "missing staged file: $stage" }
    if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash -ne $item.Hash) {
        throw "staged hash mismatch: $($item.Stage)"
    }
}
& $python -m py_compile (Join-Path $stageRoot 'ollama_proxy_server.py') (Join-Path $stageRoot 'imes_relay_mcp_server.py')
if ($LASTEXITCODE -ne 0) { throw 'staged Python compile failed' }

$protectedBefore = @{}
foreach ($port in @(8768, 8094, 8770)) { $protectedBefore[$port] = (Get-Listener $port).pid }
$listener8093Before = Get-Listener 8093 $false
$serviceStateBefore = (Get-Service -Name $serviceName).Status.ToString()

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
foreach ($item in $files) {
    $target = Join-Path $root $item.Relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "target file missing: $target" }
    $backup = Join-Path $backupRoot $item.Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
    Copy-Item -LiteralPath $target -Destination $backup -Force
}

$taskPaused = $false
$filesDeployed = $false
$rollbackApplied = $false
try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    Wait-GuardTaskIdle
    $taskPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Stopped'
    Wait-Port 8093 $false

    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-Listener $port).pid -ne $protectedBefore[$port]) { throw "protected port $port changed" }
    }

    foreach ($item in $files) {
        $target = Join-Path $root $item.Relative
        $stage = Join-Path $stageRoot $item.Stage
        $temporary = "$target.deploy_$stamp"
        Copy-Item -LiteralPath $stage -Destination $temporary -Force
        Move-Item -LiteralPath $temporary -Destination $target -Force
    }
    $filesDeployed = $true

    & $python -m py_compile (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py') (Join-Path $root '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py')
    if ($LASTEXITCODE -ne 0) { throw 'deployed Python compile failed' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true

    $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=heat-chemistry-$stamp" -TimeoutSec 30
    if ([int]$page.StatusCode -ne 200) { throw '8093 page is not HTTP 200' }
    $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/mcp/health?t=heat-chemistry-$stamp" -TimeoutSec 30
    if ([int]$health.StatusCode -ne 200) { throw '8093 MCP health is not HTTP 200' }

    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    $taskInfo = Get-ScheduledTaskInfo -TaskName $guardTaskName -TaskPath $guardTaskPath
    $taskAfter = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath
    if ($taskAfter.State.ToString() -eq 'Disabled') { throw '8093 health task was not restored' }
} catch {
    $deployError = $_
    if ($filesDeployed) {
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
            Wait-ServiceState $serviceName 'Stopped'
            Wait-Port 8093 $false
            foreach ($item in $files) {
                $target = Join-Path $root $item.Relative
                $backup = Join-Path $backupRoot $item.Relative
                Copy-Item -LiteralPath $backup -Destination $target -Force
            }
            $rollbackApplied = $true
        } catch { Write-Warning "rollback file restore failed: $($_.Exception.Message)" }
    }
    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue | Out-Null
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    throw $deployError
}

$listenersAfter = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) { $listenersAfter[$port] = (Get-Listener $port).pid }
foreach ($port in @(8768, 8094, 8770)) {
    if ($listenersAfter[$port] -ne $protectedBefore[$port]) { throw "protected PID changed on $port" }
}
$deployedHashes = @{}
foreach ($item in $files) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $root $item.Relative) -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "deployed hash mismatch: $($item.Relative)" }
    $deployedHashes[$item.Relative] = $actual
}

[ordered]@{
    schema = 'ops.8093.heat-chemistry-model-planner.v1'
    requirement_id = 'REQ-8093-AUTONOMOUS-HEAT-CHEMISTRY-MCP-20260806'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    service_state_before = $serviceStateBefore
    listener_8093_before = if ($listener8093Before) { $listener8093Before.pid } else { $null }
    listener_8093_after = $listenersAfter[8093]
    guard_paused = $taskPaused
    guard_restored = (Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath).State.ToString() -ne 'Disabled'
    guard_state = $taskAfter.State.ToString()
    guard_last_result_before_next_schedule = $taskInfo.LastTaskResult
    rollback_applied = $rollbackApplied
    protected_pids = [ordered]@{
        port_8768_before = $protectedBefore[8768]; port_8768_after = $listenersAfter[8768]
        port_8094_before = $protectedBefore[8094]; port_8094_after = $listenersAfter[8094]
        port_8770_before = $protectedBefore[8770]; port_8770_after = $listenersAfter[8770]
    }
    deployed_hashes = $deployedHashes
} | ConvertTo-Json -Depth 8
