$ErrorActionPreference = 'Stop'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$CssPayload = 'C:\Users\Administrator\AppData\Local\Temp\bf3d-furnace-summary-readability-8093.css'
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\remote_deploy_8093_furnace_summary_readability.py'
$serviceName = 'BFV4PreviewProxy8093'
$wsServiceName = 'BFV4PreviewWs8768'
$manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$config = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$python = 'C:\Program Files\Python311\python.exe'

function Wait-ServiceState {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$DesiredState,
        [int]$TimeoutSeconds = 20
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $DesiredState) { return $service }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState within ${TimeoutSeconds}s"
}

foreach ($required in @($manager, $config, $python, $CssPayload, $DeployScript)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "required deployment input is missing: $required" }
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$listen8768Before = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
if ($wsBefore.Status -ne 'Running' -or -not $listen8768Before) {
    throw 'BFV4PreviewWs8768 must remain running/listening during the 8093 deployment'
}

$deployOutput = @()
$guardPaused = $false
$guardRestored = $false
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $config | Out-Null
    $service = Wait-ServiceState -Name $serviceName -DesiredState 'Stopped' -TimeoutSeconds 15
    $guardPaused = $service.Status -eq 'Stopped'
    if (Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue) {
        throw '8093 still has a listener after the guard service stopped; deployment aborted'
    }
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)) {
        throw '8768 stopped while pausing the 8093 guard; deployment aborted'
    }

    $deployOutput = @(& $python $DeployScript --root $Root --css-payload $CssPayload 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "8093 summary-card deployment failed: $($deployOutput -join [Environment]::NewLine)"
    }
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    $service = Wait-ServiceState -Name $serviceName -DesiredState 'Running' -TimeoutSeconds 20
    $guardRestored = $service.Status -eq 'Running'
}

$deadline = [DateTime]::UtcNow.AddSeconds(20)
do {
    $listen8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue)
    if ($listen8093) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)

$listen8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
if (-not $guardRestored -or -not $listen8093 -or -not $listen8768) {
    throw "post-deploy service check failed: guard=$guardRestored, 8093=$listen8093, 8768=$listen8768"
}

$page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?t=summary-readability-20260802#overview' -TimeoutSec 5
$asset = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/assets/bf3d-furnace-summary-readability-8093.css?v=20260802-expanded7-r2' -TimeoutSec 5
$result = [ordered]@{
    schema = 'ops.8093.guard-pause-deploy-resume.v1'
    requirement_id = 'REQ-BF3D-8093-FURNACE-SUMMARY-READABILITY-20260802'
    service_before = $serviceBefore.Status.ToString()
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    ws8768_unchanged = $wsBefore.Status -eq 'Running' -and $listen8768
    listen_8093 = $listen8093
    listen_8768 = $listen8768
    http_8093 = [int]$page.StatusCode
    page_linked = $page.Content.Contains('bf3d-furnace-summary-readability-8093.css?v=20260802-expanded7-r2')
    seven_card_scope = $asset.Content.Contains('.layered-cad-stage .furnace-layer-callouts.follow-model .furnace-layer-card')
    compact_width_198 = $asset.Content.Contains('width: 198px !important')
    ellipsis_removed = $asset.Content.Contains('text-overflow: clip !important')
    units_preserved = $asset.Content.Contains('display: inline !important')
    point_billboards_untouched = -not $asset.Content.Contains('.furnace-billboard')
    deploy_output = $deployOutput
}
$result | ConvertTo-Json -Depth 8
