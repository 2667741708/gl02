$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = (Get-Location).Path
$patcher = "C:\Users\Administrator\AppData\Local\Temp\patch_8093_core_metrics_pspace_live.py"
$stagedAsset = "C:\Users\Administrator\AppData\Local\Temp\bf-core-metrics-pspace-live-8093.js"
$python = "C:\Program Files\Python311\python.exe"
$serviceName = "BFV4PreviewProxy8093"
$wsServiceName = "BFV4PreviewWs8768"
$taskPath = "\BlastFurnaceServices\"
$taskName8094 = "V3AutoPreviewProxy8094"
$marker = "REQ-8093-CORE-PSPACE-REALTIME-20260804"
$clockMarker = "REQ-8093-HEADER-SYSTEM-CLOCK-20260805"
$schema = "bf.core-metrics.pspace-live.8093.v1"
$assetName = "bf-core-metrics-pspace-live-8093.js"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

function Find-LiveFile {
    param([string]$Filter, [scriptblock]$ExtraCheck)
    $matches = @(
        Get-ChildItem -LiteralPath $root -Recurse -File -Filter $Filter -ErrorAction Stop |
            Where-Object {
                $_.FullName -notmatch "\\backups\\|\\logs\\|\\.tmp|\\.codex_stage\\" -and
                (& $ExtraCheck $_)
            }
    )
    if ($matches.Count -ne 1) {
        throw "Expected exactly one live $Filter under $root, found $($matches.Count)"
    }
    return $matches[0].FullName
}

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

if ($root -notmatch "V4_8093_PREVIEW") {
    throw "Refusing deployment outside the V4 8093 preview root: $root"
}

$targetHtml = Find-LiveFile -Filter "frontend_dashboard_v3.server.html" -ExtraCheck {
    param($file)
    Test-Path -LiteralPath (Join-Path $file.DirectoryName "assets") -PathType Container
}
$html8094 = Find-LiveFile -Filter "frontend_dashboard_v3.8094_preview.server.html" -ExtraCheck { param($file) $true }
$sharedAdapter = Find-LiveFile -Filter "bf3d-furnace-body-billboard-adapter.js" -ExtraCheck { param($file) $true }
$camera8094 = Find-LiveFile -Filter "bf3d-surface-camera-guard-8094.js" -ExtraCheck { param($file) $true }
$assetDir = Split-Path -Parent $sharedAdapter
$targetAsset = Join-Path $assetDir $assetName
$manager = Join-Path $root "tools\manage_22012_managed_services.ps1"
$config = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$backup = Join-Path $root "backups\8093_core_metrics_pspace_live_20260804\$stamp"
$backupHtml = Join-Path $backup "frontend_dashboard_v3.server.html"
$backupAsset = Join-Path $backup $assetName

foreach ($required in @($targetHtml, $html8094, $sharedAdapter, $camera8094, $patcher, $stagedAsset, $manager, $config, $python)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required deployment input is missing: $required"
    }
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
$assetExistedBefore = Test-Path -LiteralPath $targetAsset -PathType Leaf
if ($assetExistedBefore) {
    Copy-Item -LiteralPath $targetAsset -Destination $backupAsset -Force
}

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
    if (-not (Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue)) {
        throw "8770 stopped while pausing the 8093 guard"
    }

    $patchOutput = @(& $python -X utf8 $patcher --input $targetHtml 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "8093 realtime core-metric patch failed: $($patchOutput -join [Environment]::NewLine)"
    }

    $assetTemp = "$targetAsset.deploying.$stamp"
    Copy-Item -LiteralPath $stagedAsset -Destination $assetTemp -Force
    Move-Item -LiteralPath $assetTemp -Destination $targetAsset -Force

    $patchedHtml = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
    $deployedAsset = Get-Content -LiteralPath $targetAsset -Raw -Encoding UTF8
    if (
        -not $patchedHtml.Contains($marker) -or
        -not $patchedHtml.Contains($clockMarker) -or
        -not $patchedHtml.Contains("const [systemTime, setSystemTime] = useState(() => new Date())") -or
        -not $patchedHtml.Contains($assetName) -or
        -not $patchedHtml.Contains("BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093") -or
        -not $deployedAsset.Contains($schema)
    ) {
        throw "8093 realtime core-metric deployment contract is incomplete"
    }
}
catch {
    Copy-Item -LiteralPath $backupHtml -Destination $targetHtml -Force
    if ($assetExistedBefore) {
        Copy-Item -LiteralPath $backupAsset -Destination $targetAsset -Force
    } elseif (Test-Path -LiteralPath $targetAsset -PathType Leaf) {
        Remove-Item -LiteralPath $targetAsset -Force
    }
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    $running = Wait-ServiceState -Name $serviceName -DesiredState "Running" -TimeoutSeconds 30
    $guardRestored = $running.Status -eq "Running"
}

Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 30
$pageUrl = "http://127.0.0.1:8093/?core_pspace_live=$stamp#overview"
$assetUrl = "http://127.0.0.1:8093/assets/${assetName}?v=$stamp"
$response8093 = Invoke-WebRequest -UseBasicParsing -Uri $pageUrl -TimeoutSec 60
$responseAsset = Invoke-WebRequest -UseBasicParsing -Uri $assetUrl -TimeoutSec 30
if (
    $response8093.StatusCode -ne 200 -or
    -not $response8093.Content.Contains($marker) -or
    -not $response8093.Content.Contains($clockMarker) -or
    -not $response8093.Content.Contains("const [systemTime, setSystemTime] = useState(() => new Date())") -or
    -not $response8093.Content.Contains($assetName) -or
    -not $response8093.Content.Contains("BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093") -or
    $responseAsset.StatusCode -ne 200 -or
    -not $responseAsset.Content.Contains($schema)
) {
    throw "8093 did not serve the realtime core-metric contract after guard restore"
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
        schema = "ops.8093.core-metrics-pspace-live.failure.v1"
        failures = $isolationFailures
        isolation = $isolation
        hashes_before = $protectedBefore
        hashes_after = $protectedAfter
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw "Post-deploy isolation check failed: $($isolationFailures -join ', ')"
}

[ordered]@{
    schema = "ops.8093.core-metrics-pspace-live.v1"
    requirement = $marker
    backup = $backup
    service_before = $serviceBefore.Status.ToString()
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    listen_8093 = $true
    http_8093 = [int]$response8093.StatusCode
    http_asset = [int]$responseAsset.StatusCode
    marker_served = $response8093.Content.Contains($marker)
    system_clock_marker_served = $response8093.Content.Contains($clockMarker)
    schema_served = $responseAsset.Content.Contains($schema)
    pid_8094_unchanged = $isolation.pid_8094_unchanged
    pid_8768_unchanged = $isolation.pid_8768_unchanged
    pid_8770_unchanged = $isolation.pid_8770_unchanged
    protected_8094_hashes_unchanged = (
        $isolation.html_8094_hash_unchanged -and
        $isolation.shared_adapter_hash_unchanged -and
        $isolation.camera_8094_hash_unchanged
    )
    html_8093_sha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
    asset_sha256 = (Get-FileHash -LiteralPath $targetAsset -Algorithm SHA256).Hash
    patch_output = $patchOutput
} | ConvertTo-Json -Depth 6
