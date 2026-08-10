$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-8093-HTTP-STATIC-STABILITY-DEPLOY-20260806-R1
# Deliberately does not acquire the global deployment mutex.
$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$GuardTaskPath = '\BlastFurnaceServices\'
$GuardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$Manager = Join-Path $ProjectRoot 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$BackendTarget = Join-Path $ProjectRoot '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$BackendPayload = 'C:\Users\Administrator\AppData\Local\Temp\ollama_proxy_server_8093_http_stability.py'
$ProbePayload = 'C:\Users\Administrator\AppData\Local\Temp\probe_8093_http_stability.py'
$Python = 'C:\Program Files\Python311\python.exe'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $ProjectRoot "logs\deploy_backups\8093_http_static_stability_$Stamp"

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object { $_ -match ":$Port\s" -and $_ -match "LISTENING\s+(\d+)\s*$" })[0]
    if (-not $line) { return $null }
    [void]($line -match "LISTENING\s+(\d+)\s*$")
    return [int]$matches[1]
}

function Wait-ServiceState([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $Desired"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (($null -ne (Get-ListenerPid $Port)) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening"
}

function Install-Atomic([string]$Source, [string]$Target) {
    $temporary = "$Target.deploy_$Stamp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

foreach ($required in @($ProjectRoot, $Manager, $ConfigPath, $BackendTarget, $BackendPayload, $ProbePayload, $Python)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "missing required path: $required" }
}

$payloadText = Get-Content -LiteralPath $BackendPayload -Raw -Encoding UTF8
foreach ($marker in @(
    'OPS-8093-HTTP-STATIC-STABILITY-20260806-R1',
    'OPS-8093-STABLE-GLB-URL-REWRITE-20260806-R1',
    'class BlastFurnaceThreadingHTTPServer',
    'BF_8093_HTTP_REQUEST_QUEUE_SIZE'
)) {
    if (-not $payloadText.Contains($marker)) { throw "backend payload marker missing: $marker" }
}
& $Python -m py_compile $BackendPayload
if ($LASTEXITCODE -ne 0) { throw 'backend payload py_compile failed' }

$payloadHash = (Get-FileHash -LiteralPath $BackendPayload -Algorithm SHA256).Hash
$protectedBefore = [ordered]@{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedBefore[[string]$port] = Get-ListenerPid $port
    if ($null -eq $protectedBefore[[string]$port]) { throw "protected port is not listening: $port" }
}
$listenerBefore = Get-ListenerPid 8093
if ($null -eq $listenerBefore) { throw '8093 is not listening before deploy' }
if ((Get-Service -Name $ServiceName).Status.ToString() -ne 'Running') { throw '8093 service is not Running before deploy' }

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$backendBackup = Join-Path $BackupRoot 'ollama_proxy_server.py.bak'
Copy-Item -LiteralPath $BackendTarget -Destination $backendBackup -Force
$guardPaused = $false
$guardRestored = $false
$rollbackApplied = $false
$serviceStopped = $false
$deployError = $null
$probe = $null

try {
    Disable-ScheduledTask -TaskPath $GuardTaskPath -TaskName $GuardTaskName | Out-Null
    Stop-ScheduledTask -TaskPath $GuardTaskPath -TaskName $GuardTaskName -ErrorAction SilentlyContinue
    $guardPaused = $true

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState $ServiceName 'Stopped'
    Wait-Port 8093 $false
    $serviceStopped = $true

    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[[string]$port]) { throw "protected PID changed before install: $port" }
    }

    Install-Atomic $BackendPayload $BackendTarget
    if ((Get-FileHash -LiteralPath $BackendTarget -Algorithm SHA256).Hash -ne $payloadHash) { throw 'deployed backend hash mismatch' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState $ServiceName 'Running'
    Wait-Port 8093 $true
    $serviceStopped = $false

    $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?ws_port=8768#overview' -TimeoutSec 45
    if ([int]$page.StatusCode -ne 200) { throw "page HTTP $($page.StatusCode)" }
    if (-not ([string]$page.Content).Contains('GL02_FURNACE_BODY_R1.glb?v=20260806-static-stability-r1')) { throw 'served page lacks stable GLB URL' }
    if (([string]$page.Content).Contains('GL02_FURNACE_BODY_R1.glb?t=${Date.now()}')) { throw 'served page still contains random GLB URL' }

    $adapter = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/assets/bf3d-furnace-body-billboard-adapter.js?v=20260806-local-133-r1' -TimeoutSec 30
    if ([int]$adapter.StatusCode -ne 200) { throw "adapter HTTP $($adapter.StatusCode)" }
    if ([string]$adapter.Headers['Cache-Control'] -notmatch 'immutable') { throw 'versioned adapter is not immutable-cacheable' }
    if ([string]::IsNullOrWhiteSpace([string]$adapter.Headers['ETag'])) { throw 'versioned adapter lacks ETag' }

    $probeText = & $Python $ProbePayload --base-url http://127.0.0.1:8093 --rounds 3 --concurrency 8 --timeout 15
    if ($LASTEXITCODE -ne 0) { throw 'internal HTTP stability probe failed' }
    $probe = ($probeText -join "`n") | ConvertFrom-Json
    if (-not $probe.complete) { throw 'internal HTTP stability probe is incomplete' }
} catch {
    $deployError = $_
    try {
        if ((Get-Service -Name $ServiceName).Status.ToString() -ne 'Stopped') {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
            Wait-ServiceState $ServiceName 'Stopped'
            Wait-Port 8093 $false
        }
        Install-Atomic $backendBackup $BackendTarget
        $rollbackApplied = $true
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
        Wait-ServiceState $ServiceName 'Running'
        Wait-Port 8093 $true
        $serviceStopped = $false
    } catch {
        $deployError = [Exception]::new("$($deployError.Exception.Message); rollback failed: $($_.Exception.Message)")
    }
} finally {
    if ($serviceStopped -or (Get-Service -Name $ServiceName).Status.ToString() -ne 'Running') {
        try {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
            Wait-ServiceState $ServiceName 'Running'
            Wait-Port 8093 $true
        } catch {
            if (-not $deployError) { $deployError = $_ }
        }
    }
    try {
        Enable-ScheduledTask -TaskPath $GuardTaskPath -TaskName $GuardTaskName | Out-Null
        $guardRestored = $true
    } catch {
        if (-not $deployError) { $deployError = $_ }
    }
}

$protectedAfter = [ordered]@{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedAfter[[string]$port] = Get-ListenerPid $port
    if ($protectedAfter[[string]$port] -ne $protectedBefore[[string]$port] -and -not $deployError) {
        $deployError = [Exception]::new("protected PID changed after deploy: $port")
    }
}
$result = [ordered]@{
    schema = 'ops.8093.http-static-stability-deploy.v1'
    captured_at = (Get-Date).ToString('o')
    deployment_mutex_used = $false
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    rollback_applied = $rollbackApplied
    backup_root = $BackupRoot
    backend_sha256 = (Get-FileHash -LiteralPath $BackendTarget -Algorithm SHA256).Hash
    payload_sha256 = $payloadHash
    listener_8093_before = $listenerBefore
    listener_8093_after = Get-ListenerPid 8093
    protected_before = $protectedBefore
    protected_after = $protectedAfter
    probe = $probe
    ok = $null -eq $deployError
    error = if ($deployError) { $deployError.Exception.Message } else { $null }
}
$result | ConvertTo-Json -Depth 12
if ($deployError) { throw $deployError }
