$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# REQ-22012-IMES-MCP-SYNC-20260805
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$serviceConfig = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$registryPath = Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\server_registry.json'
$guardTaskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$python = 'C:\Program Files\Python311\python.exe'
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_imes_mcp_sync_stage'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\8093_imes_mcp_sync_$stamp"
$expectedMcpHash = 'B8C7611FBDCFA953E6008E0ADBA7663E911FBB3636B8D7046CC467865D8CB6FB'
$expectedCatalogHash = '244BCD4105DFE141F82AC28245D6D9219E47CACEDBB58C4E68B4A71F928F68A6'
$expectedRegistryHash = '4008A454CA79ABA7D4BBC0C1956A394CA1EDFF1547079A4A70EA11CCE81720E6'
$expectedConfigPatcherHash = '2216DA71CDCB28BE514714FA89E402B14B500A5DB38644A8FAD6DEAF5FF5A35D'
$expectedDomainRouterHash = '0BF8384CC8ED8D5DE11D1239C22A1345A8F448E60E49BB468B164AE7A7DCD021'
$expectedExtendedMcpHash = '2B0AA1656F5AEA1C884006D73F5268FB914FFC2C7877711F9AEFABE048173C00'
$expectedWebMcpHash = '565BD3B827D307357881F93B93984EED81CB75F5F56F9741FD1E6AEBCFF88EEF'
$protectedPorts = @(8768, 8094, 8770)
$files = @(
    @{
        Relative = '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'
        Stage = 'imes_relay_mcp_server.py'
        Hash = $expectedMcpHash
    },
    @{
        Relative = '高炉前端数据\智能助手\mcp\imes_full_variable_catalog.json'
        Stage = 'imes_full_variable_catalog.json'
        Hash = $expectedCatalogHash
    },
    @{
        Relative = '高炉前端数据\智能助手\backend\mcp_host\server_registry.json'
        Stage = 'server_registry.json'
        Hash = $expectedRegistryHash
    },
    @{
        Relative = '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'
        Stage = 'domain_router.py'
        Hash = $expectedDomainRouterHash
    },
    @{
        Relative = '高炉前端数据\智能助手\mcp\bf_data_extended_mcp_server.py'
        Stage = 'bf_data_extended_mcp_server.py'
        Hash = $expectedExtendedMcpHash
    },
    @{
        Relative = '高炉前端数据\智能助手\mcp\imes_web_mcp_server.py'
        Stage = 'imes_web_mcp_server.py'
        Hash = $expectedWebMcpHash
    },
    @{
        Relative = 'tools\patch_22012_8093_mcp_service_config.py'
        Stage = 'patch_22012_8093_mcp_service_config.py'
        Hash = $expectedConfigPatcherHash
    }
)

function Get-ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
        Select-Object -First 1
    if (-not $row) { throw "TCP $Port is not listening" }
    return [int]$row.OwningProcess
}

function Wait-ServiceState([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $Desired within ${TimeoutSeconds}s"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening within ${TimeoutSeconds}s"
}

function Wait-GuardTaskIdle([int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
        if ($task.State.ToString() -ne 'Running') { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$guardTaskPath$guardTaskName did not become idle within ${TimeoutSeconds}s"
}

function Assert-RemoteImesRegistry {
    $registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $imes = @($registry.servers | Where-Object { $_.server_id -eq 'imes-readonly' })
    if ($imes.Count -ne 1) { throw 'imes-readonly must appear exactly once in the remote registry' }
    if ($imes[0].script -ne '../../mcp/imes_relay_mcp_server.py') {
        throw 'imes-readonly points to an unexpected MCP script'
    }
    if ($imes[0].env_defaults.IMES_MCP_CONNECTION_MODE -ne 'direct_22012') {
        throw 'remote imes-readonly must retain IMES_MCP_CONNECTION_MODE=direct_22012'
    }
    if ($imes[0].env_defaults.IMES_RELAY_DB_HOST -ne '10.10.181.195') {
        throw 'remote imes-readonly must retain the fixed Vastbase host'
    }
}

function Assert-ProductionServiceConfig {
    $config = Get-Content -LiteralPath $serviceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $requiredEnv = [ordered]@{
        BF_QA_MCP_SERVER_REGISTRY = 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/高炉前端数据/智能助手/backend/mcp_host/server_registry.json'
        IMES_MCP_CONNECTION_MODE = 'direct_22012'
        IMES_RELAY_DB_HOST = '10.10.181.195'
        IMES_RELAY_DB_PORT = '5432'
        IMES_ACTIVE_HEAT_MAX_AGE_HOURS = '72'
        IMES_WEB_URL = 'http://10.10.181.209:8080/imes.web/'
    }
    foreach ($name in $requiredEnv.Keys) {
        if ([string]$config.env.$name -ne [string]$requiredEnv[$name]) {
            throw "production service config mismatch: $name"
        }
    }
    foreach ($name in @('IMES_DB_USER', 'IMES_DB_PASSWORD', 'IMES_WEB_USER', 'IMES_WEB_PASSWORD')) {
        if ($name -notin @($config.envMachine)) {
            throw "production service config does not inherit Machine env: $name"
        }
    }
}

foreach ($required in @($manager, $serviceConfig, $registryPath, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "required file is missing: $required"
    }
}
Assert-RemoteImesRegistry

foreach ($item in $files) {
    $stagePath = Join-Path $stageRoot $item.Stage
    if (-not (Test-Path -LiteralPath $stagePath -PathType Leaf)) {
        throw "staged file is missing: $stagePath"
    }
    $actualHash = (Get-FileHash -LiteralPath $stagePath -Algorithm SHA256).Hash
    if ($actualHash -ne $item.Hash) {
        throw "staged hash mismatch: $($item.Stage)"
    }
}

$stagedPython = @(
    (Join-Path $stageRoot 'imes_relay_mcp_server.py'),
    (Join-Path $stageRoot 'domain_router.py'),
    (Join-Path $stageRoot 'bf_data_extended_mcp_server.py'),
    (Join-Path $stageRoot 'imes_web_mcp_server.py'),
    (Join-Path $stageRoot 'patch_22012_8093_mcp_service_config.py')
)
& $python -m py_compile @stagedPython
if ($LASTEXITCODE -ne 0) { throw "staged Python compile failed: $LASTEXITCODE" }

$stagedCatalog = Join-Path $stageRoot 'imes_full_variable_catalog.json'
$catalog = Get-Content -LiteralPath $stagedCatalog -Raw -Encoding UTF8 | ConvertFrom-Json
if (@($catalog.entries).Count -ne 315) {
    throw "staged IMES variable catalog must contain 315 entries"
}

$stagedRegistryPath = Join-Path $stageRoot 'server_registry.json'
$stagedRegistry = Get-Content -LiteralPath $stagedRegistryPath -Raw -Encoding UTF8 | ConvertFrom-Json
$stagedServerIds = @($stagedRegistry.servers | ForEach-Object { [string]$_.server_id })
$expectedServerIds = @('gl02-data', 'gl02-extended', 'imes-readonly', 'imes-web-readonly')
if (($stagedServerIds -join ',') -ne ($expectedServerIds -join ',')) {
    throw "staged registry service mismatch: $($stagedServerIds -join ',')"
}
$stagedImes = @($stagedRegistry.servers | Where-Object { $_.server_id -eq 'imes-readonly' })[0]
if ($stagedImes.env_defaults.IMES_MCP_CONNECTION_MODE -ne 'direct_22012') {
    throw 'staged production registry must use direct_22012'
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne 'Running') {
    throw "$serviceName must be Running before deployment"
}
$taskBefore = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
if ($taskBefore.State.ToString() -eq 'Disabled') {
    throw '8093 health guard task is disabled before deployment'
}

$listenersBefore = [ordered]@{}
$listenersBefore['8093'] = Get-ListenerPid 8093
foreach ($port in $protectedPorts) {
    $listenersBefore[[string]$port] = Get-ListenerPid $port
}

$httpBefore = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/ollama/status?t=$stamp" -TimeoutSec 20
if ([int]$httpBefore.StatusCode -ne 200) { throw '8093 baseline HTTP is not 200' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$existing = @{}
foreach ($item in $files) {
    $target = Join-Path $root $item.Relative
    $backup = Join-Path $backupRoot $item.Relative
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
        Copy-Item -LiteralPath $target -Destination $backup -Force
        $existing[$item.Relative] = $true
    } else {
        $existing[$item.Relative] = $false
    }
}
Copy-Item -LiteralPath $registryPath -Destination (Join-Path $backupRoot 'server_registry.json.unchanged') -Force
Copy-Item -LiteralPath $serviceConfig -Destination (Join-Path $backupRoot '22012_BFV4PreviewProxy8093.json.before') -Force

$taskPaused = $false
$serviceStopped = $false
$serviceStarted = $false
$taskRestored = $false
$rollbackApplied = $false
$serviceConfigChanged = $false
try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    Wait-GuardTaskIdle
    $taskPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $serviceConfig | Out-Null
    Wait-ServiceState $serviceName 'Stopped'
    Wait-Port 8093 $false
    $serviceStopped = $true

    foreach ($port in $protectedPorts) {
        if ((Get-ListenerPid $port) -ne $listenersBefore[[string]$port]) {
            throw "protected port $port changed while 8093 was stopped"
        }
    }

    foreach ($item in $files) {
        $target = Join-Path $root $item.Relative
        $stage = Join-Path $stageRoot $item.Stage
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        $temporary = "$target.deploy_$stamp"
        Copy-Item -LiteralPath $stage -Destination $temporary -Force
        Move-Item -LiteralPath $temporary -Destination $target -Force
    }

    $configPatcher = Join-Path $root 'tools\patch_22012_8093_mcp_service_config.py'
    $configPatchArgs = @('-X', 'utf8', $configPatcher, '--config', $serviceConfig)
    $configPatchOutput = & $python @configPatchArgs
    if ($LASTEXITCODE -ne 0) { throw "service config patch failed: $LASTEXITCODE" }
    $configPatchResult = $configPatchOutput | ConvertFrom-Json
    $serviceConfigChanged = [bool]$configPatchResult.changed

    $deployedPython = @(
        (Join-Path $root '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'),
        (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'),
        (Join-Path $root '高炉前端数据\智能助手\mcp\bf_data_extended_mcp_server.py'),
        (Join-Path $root '高炉前端数据\智能助手\mcp\imes_web_mcp_server.py'),
        (Join-Path $root 'tools\patch_22012_8093_mcp_service_config.py')
    )
    & $python -m py_compile @deployedPython
    if ($LASTEXITCODE -ne 0) { throw "deployed Python compile failed: $LASTEXITCODE" }
    Assert-RemoteImesRegistry
    Assert-ProductionServiceConfig

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $serviceConfig | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    $serviceStarted = $true

    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Start-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath
    Wait-GuardTaskIdle
    $taskRestored = (Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath).State.ToString() -ne 'Disabled'
    $taskInfo = Get-ScheduledTaskInfo -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
    if ($taskInfo.LastTaskResult -ne 0) {
        throw "8093 health guard task failed: $($taskInfo.LastTaskResult)"
    }
} catch {
    $deployError = $_
    if ($serviceStopped) {
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $serviceConfig | Out-Null
            Wait-ServiceState $serviceName 'Stopped'
            Wait-Port 8093 $false
            foreach ($item in $files) {
                $target = Join-Path $root $item.Relative
                $backup = Join-Path $backupRoot $item.Relative
                if ($existing[$item.Relative]) {
                    Copy-Item -LiteralPath $backup -Destination $target -Force
                } else {
                    Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
                }
            }
            Copy-Item -LiteralPath (Join-Path $backupRoot '22012_BFV4PreviewProxy8093.json.before') `
                -Destination $serviceConfig -Force
            $rollbackApplied = $true
        } catch {
            Write-Warning "rollback failed: $($_.Exception.Message)"
        }
    }
    if ($taskPaused) {
        Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $serviceConfig | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    throw $deployError
}

$listenersAfter = [ordered]@{}
$listenersAfter['8093'] = Get-ListenerPid 8093
foreach ($port in $protectedPorts) {
    $listenersAfter[[string]$port] = Get-ListenerPid $port
}

foreach ($port in $protectedPorts) {
    if ($listenersAfter[[string]$port] -ne $listenersBefore[[string]$port]) {
        throw "protected port $port PID changed after deployment"
    }
}

$httpAfter = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/ollama/status?t=$stamp" -TimeoutSec 20
if ([int]$httpAfter.StatusCode -ne 200) { throw '8093 HTTP is not 200 after deployment' }
Assert-RemoteImesRegistry
Assert-ProductionServiceConfig

$deployedHashes = [ordered]@{}
foreach ($item in $files) {
    $target = Join-Path $root $item.Relative
    $deployedHashes[$item.Relative] = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($deployedHashes[$item.Relative] -ne $item.Hash) {
        throw "deployed hash mismatch: $($item.Relative)"
    }
}

$result = [ordered]@{
    schema = 'ops.8093.imes-mcp-sync.guarded-deploy.v1'
    requirement_id = 'REQ-22012-IMES-MCP-SYNC-20260805'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    rollback_applied = $rollbackApplied
    task_paused = $taskPaused
    task_restored = $taskRestored
    service_restarted = $serviceStarted
    http_8093 = [int]$httpAfter.StatusCode
    remote_connection_mode = 'direct_22012'
    service_config_changed = $serviceConfigChanged
    registered_services = $expectedServerIds
    catalog_entries = @($catalog.entries).Count
    hashes = $deployedHashes
    pids = @(
        foreach ($port in @(8093, 8768, 8094, 8770)) {
            [ordered]@{
                port = $port
                before = $listenersBefore[[string]$port]
                after = $listenersAfter[[string]$port]
            }
        }
    )
}
$resultPath = Join-Path $backupRoot 'deployment_result.json'
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultPath -Encoding UTF8
$result | ConvertTo-Json -Depth 8
