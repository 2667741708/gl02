$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = if ($env:BF_8093_DEPLOY_PROJECT_ROOT) { $env:BF_8093_DEPLOY_PROJECT_ROOT } else { 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' }
$ReleaseZip = if ($env:BF_8093_DEPLOY_RELEASE_ZIP) { $env:BF_8093_DEPLOY_RELEASE_ZIP } else { 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_frontend_release.zip' }
$AllowDowngrade = $env:BF_8093_ALLOW_DOWNGRADE -eq '1'

# OPS-8093-FRONTEND-FAST-RELEASE-20260806
# The user explicitly requested that this deployer must not acquire the global deployment mutex.
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $ProjectRoot 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$frontendRoot = Join-Path $ProjectRoot '高炉前端数据'
$activeManifestPath = Join-Path $frontendRoot '8093-active-release.json'
$guardTaskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stageRoot = Join-Path $ProjectRoot ".deploy_staging\8093_frontend_$stamp"
$backupRoot = Join-Path $ProjectRoot "logs\deploy_backups\8093_frontend_$stamp"

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object { $_ -match ":$Port\s" -and $_ -match "LISTENING\s+(\d+)\s*$" })[0]
    if (-not $line) { return $null }
    [void]($line -match "LISTENING\s+(\d+)\s*$")
    return [int]$matches[1]
}

function Wait-ServiceState([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $DesiredState) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = $null -ne (Get-ListenerPid $Port)
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening"
}

function Install-Atomic([string]$Source, [string]$Target) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    $temporary = "$Target.deploy_$stamp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

foreach ($required in @($ProjectRoot, $frontendRoot, $manager, $configPath, $ReleaseZip)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "missing required path: $required" }
}

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
Expand-Archive -LiteralPath $ReleaseZip -DestinationPath $stageRoot -Force
$manifestPath = Join-Path $stageRoot 'release-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'release manifest is missing' }
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 'ops.8093.frontend-release.v1') { throw "unsupported release schema: $($manifest.schema)" }
if ([string]::IsNullOrWhiteSpace([string]$manifest.release_id)) { throw 'release id is empty' }
if ([bool]$manifest.deployment_mutex_required) { throw 'manifest unexpectedly requires a deployment mutex' }

$activeBefore = $null
if (Test-Path -LiteralPath $activeManifestPath -PathType Leaf) {
    $activeBefore = Get-Content -Raw -Encoding UTF8 -LiteralPath $activeManifestPath | ConvertFrom-Json
    if (-not $AllowDowngrade -and [string]$activeBefore.release_id -gt [string]$manifest.release_id) {
        throw "downgrade rejected: active=$($activeBefore.release_id), requested=$($manifest.release_id)"
    }
}

foreach ($file in @($manifest.files)) {
    $target = Join-Path $frontendRoot ([string]$file.relative_path)
    if ($file.mode -eq 'deploy') {
        $source = Join-Path $stageRoot ([string]$file.archive_path)
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "staged file is missing: $source" }
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne [string]$file.sha256) { throw "staged hash mismatch: $source" }
    } elseif ($file.mode -eq 'verify_only') {
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "shared dependency is missing: $target" }
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne [string]$file.sha256) { throw "shared dependency hash mismatch; 8094-safe deploy aborted: $target" }
    } else {
        throw "unsupported file mode: $($file.mode)"
    }
}

$pageStage = Join-Path $stageRoot 'payload\frontend_dashboard_v3.server.html'
$pageText = [IO.File]::ReadAllText($pageStage, [Text.Encoding]::UTF8)
foreach ($marker in @($manifest.page_markers)) {
    if (-not $pageText.Contains([string]$marker)) { throw "page marker is missing: $marker" }
}
foreach ($reference in @($manifest.forbidden_page_references)) {
    if ($pageText.Contains([string]$reference)) { throw "forbidden page reference remains: $reference" }
}

$protectedBefore = [ordered]@{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedBefore[[string]$port] = Get-ListenerPid $port
    if ($null -eq $protectedBefore[[string]$port]) { throw "protected port is not listening before deploy: $port" }
}
$listener8093Before = Get-ListenerPid 8093
if ((Get-Service -Name $serviceName -ErrorAction Stop).Status.ToString() -ne 'Running') { throw '8093 service must be Running before deploy' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backupEntries = @()
foreach ($file in @($manifest.files | Where-Object { $_.mode -eq 'deploy' })) {
    $target = Join-Path $frontendRoot ([string]$file.relative_path)
    $backup = Join-Path $backupRoot (([string]$file.relative_path -replace '[:\\/]', '_') + '.bak')
    $existed = Test-Path -LiteralPath $target -PathType Leaf
    if ($existed) { Copy-Item -LiteralPath $target -Destination $backup -Force }
    $backupEntries += [pscustomobject]@{ target = $target; backup = $backup; existed = $existed }
}
$activeBackup = Join-Path $backupRoot '8093-active-release.json.bak'
$activeExisted = Test-Path -LiteralPath $activeManifestPath -PathType Leaf
if ($activeExisted) { Copy-Item -LiteralPath $activeManifestPath -Destination $activeBackup -Force }

$guardPaused = $false
$serviceStopped = $false
$rollbackApplied = $false
$deployed = $false
$pageResponse = $null
try {
    Disable-ScheduledTask -TaskPath $guardTaskPath -TaskName $guardTaskName | Out-Null
    Stop-ScheduledTask -TaskPath $guardTaskPath -TaskName $guardTaskName -ErrorAction SilentlyContinue
    $guardPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Stopped'
    Wait-Port 8093 $false
    $serviceStopped = $true

    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[[string]$port]) { throw "protected PID changed before file install: $port" }
    }

    foreach ($file in @($manifest.files | Where-Object { $_.mode -eq 'deploy' })) {
        $source = Join-Path $stageRoot ([string]$file.archive_path)
        $target = Join-Path $frontendRoot ([string]$file.relative_path)
        Install-Atomic $source $target
    }
    Install-Atomic $manifestPath $activeManifestPath
    $deployed = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    $serviceStopped = $false

    $pageResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?release=$($manifest.release_id)#overview" -TimeoutSec 45
    if ([int]$pageResponse.StatusCode -ne 200) { throw "8093 page returned HTTP $($pageResponse.StatusCode)" }
    foreach ($marker in @($manifest.page_markers)) {
        if (-not ([string]$pageResponse.Content).Contains([string]$marker)) { throw "served page marker is missing: $marker" }
    }
    $modelResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/models/GL02_FURNACE_BODY_R1.glb?release=$($manifest.release_id)" -TimeoutSec 30
    if ([int]$modelResponse.StatusCode -ne 200) { throw "133-point model returned HTTP $($modelResponse.StatusCode)" }

    foreach ($file in @($manifest.files | Where-Object { $_.mode -eq 'deploy' })) {
        $target = Join-Path $frontendRoot ([string]$file.relative_path)
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne [string]$file.sha256) { throw "deployed hash mismatch: $target" }
    }
} catch {
    $deployError = $_
    if ($deployed) {
        try {
            if ((Get-Service -Name $serviceName).Status.ToString() -ne 'Stopped') {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
                Wait-ServiceState $serviceName 'Stopped'
                Wait-Port 8093 $false
            }
            foreach ($entry in $backupEntries) {
                if ($entry.existed) {
                    Install-Atomic $entry.backup $entry.target
                } elseif (Test-Path -LiteralPath $entry.target) {
                    Remove-Item -LiteralPath $entry.target -Force
                }
            }
            if ($activeExisted) {
                Install-Atomic $activeBackup $activeManifestPath
            } elseif (Test-Path -LiteralPath $activeManifestPath) {
                Remove-Item -LiteralPath $activeManifestPath -Force
            }
            $rollbackApplied = $true
        } catch {
            Write-Warning "rollback failed: $($_.Exception.Message)"
        }
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    $serviceStopped = $false
    throw $deployError
} finally {
    if ($serviceStopped) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    }
    if ($guardPaused) {
        Enable-ScheduledTask -TaskPath $guardTaskPath -TaskName $guardTaskName -ErrorAction SilentlyContinue | Out-Null
    }
    Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
}

$protectedAfter = [ordered]@{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedAfter[[string]$port] = Get-ListenerPid $port
    if ($protectedAfter[[string]$port] -ne $protectedBefore[[string]$port]) { throw "protected PID changed after deploy: $port" }
}

[ordered]@{
    schema = 'ops.8093.frontend-release-deploy-result.v1'
    requirement_id = 'OPS-8093-FRONTEND-FAST-RELEASE-20260806'
    release_id = [string]$manifest.release_id
    deployed_at = (Get-Date).ToString('o')
    deployment_mutex_used = $false
    downgrade_allowed = [bool]$AllowDowngrade
    backup_root = $backupRoot
    active_manifest = $activeManifestPath
    guard_paused = $guardPaused
    guard_restored = (Get-ScheduledTask -TaskPath $guardTaskPath -TaskName $guardTaskName).State.ToString() -ne 'Disabled'
    service_state = (Get-Service -Name $serviceName).Status.ToString()
    http_status = [int]$pageResponse.StatusCode
    listener_8093_before = $listener8093Before
    listener_8093_after = Get-ListenerPid 8093
    protected_pids_before = $protectedBefore
    protected_pids_after = $protectedAfter
    rollback_applied = $rollbackApplied
} | ConvertTo-Json -Depth 8
