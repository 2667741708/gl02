$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$targetHtml = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$html8094 = Join-Path $root "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$sharedAdapter = Join-Path $root "高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js"
$camera8094 = Join-Path $root "高炉前端数据\assets\bf3d-surface-camera-guard-8094.js"
$patcher = "C:\Users\Administrator\AppData\Local\Temp\patch_8094_cad_bottom_band.py"
$manager = Join-Path $root "tools\manage_22012_managed_services.ps1"
$config = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$python = "C:\Program Files\Python311\python.exe"
$serviceName = "BFV4PreviewProxy8093"
$wsServiceName = "BFV4PreviewWs8768"
$taskPath = "\BlastFurnaceServices\"
$taskName8094 = "V3AutoPreviewProxy8094"
$revisionMarker = "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8093_cad_bottom_band_20260804\$stamp"
$backupHtml = Join-Path $backup "frontend_dashboard_v3.server.html"

function Wait-ServiceState {
    param([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port $Port did not reach listening=$Listening within ${TimeoutSeconds}s"
}

foreach ($required in @($targetHtml, $html8094, $sharedAdapter, $camera8094, $patcher, $manager, $config, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required deployment input is missing: $required" }
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$task8094Before = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName8094 -ErrorAction Stop
$listener8094Before = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
$listener8768Before = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop | Select-Object -First 1
$listener8770Before = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction Stop | Select-Object -First 1
if ($serviceBefore.Status.ToString() -ne "Running" -or $wsBefore.Status.ToString() -ne "Running" -or $task8094Before.State.ToString() -ne "Running") {
    throw "8093 guard, 8768 service, and 8094 task must all be running before deployment"
}

$protectedBefore = [ordered]@{
    html8094 = (Get-FileHash -LiteralPath $html8094 -Algorithm SHA256).Hash
    sharedAdapter = (Get-FileHash -LiteralPath $sharedAdapter -Algorithm SHA256).Hash
    camera8094 = (Get-FileHash -LiteralPath $camera8094 -Algorithm SHA256).Hash
}
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination $backupHtml -Force

$guardPaused = $false
$guardRestored = $false
$patchOutput = @()
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $config | Out-Null
    $stopped = Wait-ServiceState -Name $serviceName -DesiredState "Stopped" -TimeoutSeconds 20
    Wait-PortState -Port 8093 -Listening $false -TimeoutSeconds 20
    $guardPaused = $stopped.Status -eq "Stopped"
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)) {
        throw "8768 stopped while pausing the 8093 guard"
    }

    $patchOutput = @(& $python -X utf8 $patcher --path $targetHtml --scope 8093 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "8093 bottom-band patch failed: $($patchOutput -join [Environment]::NewLine)" }
    $patchedHtml = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
    if (
        -not $patchedHtml.Contains("BUG-BF3D-CAD-BOTTOM-BAND-20260804") -or
        -not $patchedHtml.Contains($revisionMarker) -or
        -not $patchedHtml.Contains("padding-bottom: 0 !important") -or
        -not $patchedHtml.Contains("bottom: 0 !important")
    ) {
        throw "8093 patched HTML is missing the required bottom-band fix"
    }
}
catch {
    Copy-Item -LiteralPath $backupHtml -Destination $targetHtml -Force
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    $running = Wait-ServiceState -Name $serviceName -DesiredState "Running" -TimeoutSeconds 30
    $guardRestored = $running.Status -eq "Running"
}

Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 30
$response8093 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cad_bottom_band_fix=$stamp#overview" -TimeoutSec 60
if (
    $response8093.StatusCode -ne 200 -or
    -not $response8093.Content.Contains("BUG-BF3D-CAD-BOTTOM-BAND-20260804") -or
    -not $response8093.Content.Contains($revisionMarker)
) {
    throw "8093 did not serve the CAD bottom-band fix after guard restore"
}

$listener8094After = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
$listener8768After = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop | Select-Object -First 1
$listener8770After = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction Stop | Select-Object -First 1
$task8094After = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName8094 -ErrorAction Stop
$protectedAfter = [ordered]@{
    html8094 = (Get-FileHash -LiteralPath $html8094 -Algorithm SHA256).Hash
    sharedAdapter = (Get-FileHash -LiteralPath $sharedAdapter -Algorithm SHA256).Hash
    camera8094 = (Get-FileHash -LiteralPath $camera8094 -Algorithm SHA256).Hash
}
$isolation = [ordered]@{
    guard_paused = [bool]$guardPaused
    guard_restored = [bool]$guardRestored
    task_8094_running = $task8094After.State.ToString() -eq "Running"
    pid_8094_unchanged = [int]$listener8094After.OwningProcess -eq [int]$listener8094Before.OwningProcess
    pid_8768_unchanged = [int]$listener8768After.OwningProcess -eq [int]$listener8768Before.OwningProcess
    pid_8770_unchanged = [int]$listener8770After.OwningProcess -eq [int]$listener8770Before.OwningProcess
    html_8094_hash_unchanged = $protectedAfter.html8094 -eq $protectedBefore.html8094
    shared_adapter_hash_unchanged = $protectedAfter.sharedAdapter -eq $protectedBefore.sharedAdapter
    camera_8094_hash_unchanged = $protectedAfter.camera8094 -eq $protectedBefore.camera8094
}
$isolationFailures = @($isolation.GetEnumerator() | Where-Object { -not [bool]$_.Value } | ForEach-Object { $_.Key })
if ($isolationFailures.Count -gt 0) {
    [ordered]@{
        schema = "ops.8093.guard-pause-deploy-resume.failure.v1"
        failures = $isolationFailures
        isolation = $isolation
        pid_before = [ordered]@{
            port8094 = [int]$listener8094Before.OwningProcess
            port8768 = [int]$listener8768Before.OwningProcess
            port8770 = [int]$listener8770Before.OwningProcess
        }
        pid_after = [ordered]@{
            port8094 = [int]$listener8094After.OwningProcess
            port8768 = [int]$listener8768After.OwningProcess
            port8770 = [int]$listener8770After.OwningProcess
        }
        hashes_before = $protectedBefore
        hashes_after = $protectedAfter
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw "post-deploy isolation check failed: $($isolationFailures -join ', ')"
}

[ordered]@{
    schema = "ops.8093.guard-pause-deploy-resume.v1"
    bug_id = "BUG-BF3D-CAD-BOTTOM-BAND-20260804"
    backup = $backup
    service_before = $serviceBefore.Status.ToString()
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    listen_8093 = $true
    http_8093 = [int]$response8093.StatusCode
    marker_served = $response8093.Content.Contains("BUG-BF3D-CAD-BOTTOM-BAND-20260804")
    revision_marker_served = $response8093.Content.Contains($revisionMarker)
    pid_8094_unchanged = $isolation.pid_8094_unchanged
    pid_8768_unchanged = $isolation.pid_8768_unchanged
    pid_8770_unchanged = $isolation.pid_8770_unchanged
    protected_8094_hashes_unchanged = (
        $isolation.html_8094_hash_unchanged -and
        $isolation.shared_adapter_hash_unchanged -and
        $isolation.camera_8094_hash_unchanged
    )
    html_8093_sha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
    patch_output = $patchOutput
} | ConvertTo-Json -Depth 6
