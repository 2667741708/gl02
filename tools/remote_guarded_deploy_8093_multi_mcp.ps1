$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-8093-MULTI-MCP-HOST-20260805
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$guardTaskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$python = 'C:\Program Files\Python311\python.exe'
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_multi_mcp_stage'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\8093_multi_mcp_$stamp"
$expectedBackendHash = 'B7C207C42678D459CFCF4F688D2E04994D61109FBE555BF1BB72329A699AC11C'

$files = @(
    @{ Relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'; Stage = 'ollama_proxy_server.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\__init__.py'; Stage = 'mcp_host\__init__.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\server_registry.py'; Stage = 'mcp_host\server_registry.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'; Stage = 'mcp_host\domain_router.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\client_manager.py'; Stage = 'mcp_host\client_manager.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\cross_source_plan.py'; Stage = 'mcp_host\cross_source_plan.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'; Stage = 'mcp_host\cross_source_executor.py' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_host\server_registry.json'; Stage = 'mcp_host\server_registry.json' },
    @{ Relative = '高炉前端数据\智能助手\backend\mcp_conversation_context.py'; Stage = 'mcp_conversation_context.py' },
    @{ Relative = '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'; Stage = 'imes_relay_mcp_server.py' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\business_object.schema.json'; Stage = 'catalog\business_object.schema.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\catalog_manifest.json'; Stage = 'catalog\catalog_manifest.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\sensors.json'; Stage = 'catalog\sensors.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\heat_analysis.json'; Stage = 'catalog\heat_analysis.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\calculation_tools.json'; Stage = 'catalog\calculation_tools.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\chart_capabilities.json'; Stage = 'catalog\chart_capabilities.json' },
    @{ Relative = '高炉前端数据\智能助手\mcp\catalog\knowledge_assets.json'; Stage = 'catalog\knowledge_assets.json' },
    @{ Relative = 'tools\patch_22012_8093_mcp_service_config.py'; Stage = 'patch_22012_8093_mcp_service_config.py' }
)

function Get-Listener([int]$Port) {
    $row = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)[0]
    if (-not $row) { throw "TCP $Port is not listening" }
    return [pscustomobject]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Wait-ServiceState([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
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
        if ($task.State.ToString() -ne 'Running') { return $task }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$guardTaskPath$guardTaskName did not become idle within ${TimeoutSeconds}s"
}

foreach ($required in @($manager, $configPath, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file is missing: $required" }
}
foreach ($item in $files) {
    $stagePath = Join-Path $stageRoot $item.Stage
    if (-not (Test-Path -LiteralPath $stagePath -PathType Leaf)) { throw "staged file is missing: $stagePath" }
}
$stagedBackend = Join-Path $stageRoot 'ollama_proxy_server.py'
if ((Get-FileHash -LiteralPath $stagedBackend -Algorithm SHA256).Hash -ne $expectedBackendHash) {
    throw 'staged ollama_proxy_server.py hash does not match the approved local implementation'
}
& $python -m py_compile $stagedBackend (Join-Path $stageRoot 'mcp_host\server_registry.py') (Join-Path $stageRoot 'mcp_host\domain_router.py') (Join-Path $stageRoot 'mcp_host\client_manager.py') (Join-Path $stageRoot 'mcp_host\cross_source_plan.py') (Join-Path $stageRoot 'mcp_host\cross_source_executor.py') (Join-Path $stageRoot 'mcp_conversation_context.py') (Join-Path $stageRoot 'imes_relay_mcp_server.py') (Join-Path $stageRoot 'patch_22012_8093_mcp_service_config.py')
if ($LASTEXITCODE -ne 0) { throw "staged Python compile failed: $LASTEXITCODE" }
$stagedRegistry = Get-Content -LiteralPath (Join-Path $stageRoot 'mcp_host\server_registry.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$stagedServerIds = @($stagedRegistry.servers | ForEach-Object { [string]$_.server_id })
if (($stagedServerIds -join ',') -ne 'gl02-data,gl02-extended,imes-readonly,imes-web-readonly') { throw "staged registry mismatch: $($stagedServerIds -join ',')" }
$stagedManifest = Get-Content -LiteralPath (Join-Path $stageRoot 'catalog\catalog_manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (@($stagedManifest.files).Count -lt 5) { throw 'staged catalog manifest is incomplete' }

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne 'Running') { throw "$serviceName must be Running before deployment" }
$taskBefore = Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
if ($taskBefore.State.ToString() -eq 'Disabled') { throw '8093 health guard task is disabled before deployment' }
$listenersBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) { $listenersBefore[$port] = Get-Listener $port }
$page8093Before = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=multi-mcp-before-$stamp" -TimeoutSec 20
$page8094Before = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?t=multi-mcp-before-$stamp" -TimeoutSec 20
if ([int]$page8093Before.StatusCode -ne 200 -or [int]$page8094Before.StatusCode -ne 200) { throw '8093/8094 baseline HTTP is not 200' }

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

$taskPaused = $false
$serviceStopped = $false
$serviceStarted = $false
$taskRestored = $false
$rollbackApplied = $false
try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    [void](Wait-GuardTaskIdle)
    $taskPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState $serviceName 'Stopped')
    Wait-Port 8093 $false
    $serviceStopped = $true
    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-Listener $port).pid -ne $listenersBefore[$port].pid) { throw "protected port $port changed while 8093 was stopped" }
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
    & $python -X utf8 $configPatcher --config $configPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "service config patch failed: $LASTEXITCODE" }
    & $python -m py_compile (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\server_registry.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\domain_router.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\client_manager.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\cross_source_plan.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py') (Join-Path $root '高炉前端数据\智能助手\backend\mcp_conversation_context.py') (Join-Path $root '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py') (Join-Path $root 'tools\patch_22012_8093_mcp_service_config.py')
    if ($LASTEXITCODE -ne 0) { throw "deployed Python compile failed: $LASTEXITCODE" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState $serviceName 'Running')
    Wait-Port 8093 $true
    $serviceStarted = $true
    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Start-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath
    [void](Wait-GuardTaskIdle)
    $taskRestored = (Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath).State.ToString() -ne 'Disabled'
    $taskInfo = Get-ScheduledTaskInfo -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction Stop
    if ($taskInfo.LastTaskResult -ne 0) { throw "8093 health guard task failed: $($taskInfo.LastTaskResult)" }
} catch {
    $deployError = $_
    if ($serviceStopped) {
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
            [void](Wait-ServiceState $serviceName 'Stopped')
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
            $rollbackApplied = $true
        } catch { Write-Warning "rollback failed: $($_.Exception.Message)" }
    }
    if ($taskPaused) {
        Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    [void](Wait-ServiceState $serviceName 'Running')
    Wait-Port 8093 $true
    throw $deployError
}

$listenersAfter = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) { $listenersAfter[$port] = Get-Listener $port }
$page8093After = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=multi-mcp-after-$stamp" -TimeoutSec 20
$page8094After = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?t=multi-mcp-after-$stamp" -TimeoutSec 20
$mcpHealthAfter = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/mcp/health?t=multi-mcp-after-$stamp" -TimeoutSec 20
$mcpHealthJson = $mcpHealthAfter.Content | ConvertFrom-Json
$checks = [ordered]@{
    task_paused = $taskPaused
    task_restored = $taskRestored
    task_result_zero = $taskInfo.LastTaskResult -eq 0
    service_started = $serviceStarted
    service_8093_pid_changed = $listenersBefore[8093].pid -ne $listenersAfter[8093].pid
    ws_8768_pid_unchanged = $listenersBefore[8768].pid -eq $listenersAfter[8768].pid
    preview_8094_pid_unchanged = $listenersBefore[8094].pid -eq $listenersAfter[8094].pid
    db_bridge_8770_pid_unchanged = $listenersBefore[8770].pid -eq $listenersAfter[8770].pid
    http_8093 = [int]$page8093After.StatusCode
    http_8094 = [int]$page8094After.StatusCode
    mcp_health_http = [int]$mcpHealthAfter.StatusCode
    mcp_health_ok = [bool]$mcpHealthJson.ok
    mcp_cross_source_modules = [bool]$mcpHealthJson.checks.cross_source_modules_present
    mcp_registry_loaded = [bool]$mcpHealthJson.checks.registry_loaded
    mcp_catalog_present = [bool]$mcpHealthJson.checks.catalog_manifest_present
    backend_hash = (Get-FileHash -LiteralPath (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py') -Algorithm SHA256).Hash
    registry_present = Test-Path -LiteralPath (Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\server_registry.json')
}
$failed = @($checks.Keys | Where-Object { ($_ -like 'http_*' -and [int]$checks[$_] -ne 200) -or ($_ -like '*unchanged' -and -not [bool]$checks[$_]) -or ($_ -eq 'service_8093_pid_changed' -and -not [bool]$checks[$_]) -or ($_ -eq 'task_result_zero' -and -not [bool]$checks[$_]) -or ($_ -eq 'task_restored' -and -not [bool]$checks[$_]) -or ($_ -in @('registry_present','mcp_health_ok','mcp_cross_source_modules','mcp_registry_loaded','mcp_catalog_present') -and -not [bool]$checks[$_]) })
if ($failed.Count -gt 0) { throw "post-deployment checks failed: $($failed -join ', ')" }
$deployedHashes = [ordered]@{}
foreach ($item in $files) {
    $deployedHashes[$item.Relative] = (Get-FileHash -LiteralPath (Join-Path $root $item.Relative) -Algorithm SHA256).Hash
}

[ordered]@{
    schema = 'ops.8093.multi-mcp.guarded-deploy.v1'
    requirement_id = 'OPS-8093-MULTI-MCP-HOST-20260805'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    rollback_applied = $rollbackApplied
    checks = $checks
    deployed_hashes = $deployedHashes
    pids = @(
        foreach ($port in @(8093, 8768, 8094, 8770)) {
            [ordered]@{ port = $port; before = $listenersBefore[$port].pid; after = $listenersAfter[$port].pid }
        }
    )
    deployed_files = @($files.Relative)
} | ConvertTo-Json -Depth 8
