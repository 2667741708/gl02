$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$stageRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Temp\bf3d_billboard_pspace_live"
$stageAdapter = Join-Path $stageRoot "bf3d-furnace-body-billboard-adapter.js"
$targetAdapter = Join-Path $root "高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js"
$targetHtml = Join-Path $root "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V4BillboardPspace8770"
$cacheVersion = "20260726-viewport-wheel-r8"

foreach ($path in @($stageAdapter, $targetAdapter, $targetHtml)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path is missing: $path" }
}
$adapterText = Get-Content -LiteralPath $stageAdapter -Raw -Encoding UTF8
foreach ($marker in @("installBackgroundControl", "installViewportLayoutStyle", "installWheelZoomController", "mountRetryDelayMs", "fitFullModel", "soft-light", "__BF3D_BILLBOARD_PSPACE_LIVE__", '"8770"')) {
    if (-not $adapterText.Contains($marker)) { throw "Adapter marker missing: $marker" }
}

$taskBefore = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$listener8770Before = Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction Stop | Select-Object -First 1
$listener8768Before = Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction Stop | Select-Object -First 1
if ($taskBefore.State -ne "Running" -or -not $listener8770Before -or -not $listener8768Before) {
    throw "Existing 8768/8770 runtime must be healthy before the frontend-only deployment"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8094_billboard_viewport_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetAdapter -Destination (Join-Path $backup "bf3d-furnace-body-billboard-adapter.js") -Force
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force
$deployed = $false

function Invoke-HttpWithRetry {
    param([Parameter(Mandatory = $true)][string]$Uri)
    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            return Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60
        }
        catch {
            $lastError = $_
            if ($attempt -lt 3) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

try {
    Copy-Item -LiteralPath $stageAdapter -Destination $targetAdapter -Force
    $html = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
    $pattern = "assets/bf3d-furnace-body-billboard-adapter\.js(?:\?v=[^`"']*)?"
    if ($html -notmatch $pattern) { throw "8094 HTML adapter reference was not found" }
    $html = [regex]::Replace(
        $html,
        $pattern,
        "assets/bf3d-furnace-body-billboard-adapter.js?v=$cacheVersion",
        1
    )
    [IO.File]::WriteAllText($targetHtml, $html, [Text.UTF8Encoding]::new($false))

    $http = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/?billboard_background=$stamp"
    $adapterHttp = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/assets/bf3d-furnace-body-billboard-adapter.js?v=$cacheVersion"
    if ($http.StatusCode -ne 200 -or $http.Content -notmatch [regex]::Escape($cacheVersion)) {
        throw "8094 HTML did not serve the background-control adapter version"
    }
    foreach ($marker in @("installBackgroundControl", "installViewportLayoutStyle", "installWheelZoomController", "mountRetryDelayMs", "fitFullModel", "soft-light", '"8770"')) {
        if ($adapterHttp.Content -notmatch [regex]::Escape($marker)) {
            throw "Served adapter marker missing: $marker"
        }
    }

    $taskAfter = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $listener8770After = Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction Stop | Select-Object -First 1
    $listener8768After = Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction Stop | Select-Object -First 1
    if (
        $taskAfter.State -ne "Running" -or
        -not $listener8770After -or
        -not $listener8768After -or
        [int]$listener8770After.OwningProcess -ne [int]$listener8770Before.OwningProcess -or
        [int]$listener8768After.OwningProcess -ne [int]$listener8768Before.OwningProcess
    ) {
        throw "Frontend-only deployment disturbed the existing realtime runtime"
    }

    $deployed = $true
    [ordered]@{
        ok = $true
        backup = $backup
        cacheVersion = $cacheVersion
        http8094 = $http.StatusCode
        task8770 = $taskAfter.State.ToString()
        process8770Unchanged = $true
        process8768Unchanged = $true
        adapterSha256 = (Get-FileHash -LiteralPath $targetAdapter -Algorithm SHA256).Hash
        htmlSha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
    } | ConvertTo-Json -Depth 4
}
catch {
    Copy-Item -LiteralPath (Join-Path $backup "bf3d-furnace-body-billboard-adapter.js") -Destination $targetAdapter -Force
    Copy-Item -LiteralPath (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Destination $targetHtml -Force
    throw
}
finally {
    if (-not $deployed) { Write-Warning "Frontend deployment rolled back from $backup" }
}
