$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$stagedPath = Join-Path $root "logs\frontend_dashboard_v3.adaptive_20260716.staged.html"
$expectedHash = "4F0D80F45218565ABA5F8A0EB28C30882E10067745F88690B288039366C3CCEE"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targets = [ordered]@{
    "8093" = Join-Path $frontend "frontend_dashboard_v3.server.html"
    "8094" = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
}
$requiredMarkers = @(
    "BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716",
    "v3-overview-adaptive-final",
    "minmax(320px, 27fr) minmax(0, 45fr) minmax(320px, 28fr)",
    "@container overview-core-panel (min-width: 430px)",
    "@media(max-height:820px) and (min-width:1280px)",
    "bf-engine-cockpit .bf-risk-insight-grid",
    "REQ-8093-THERMAL-DIAGNOSIS-DISPLAY-20260716",
    "REQ-8093-CORE-SPARK-DETAIL-CORRELATION-20260715",
    "topbar branded-topbar"
)

function Get-TargetState {
    param([string]$Path)
    $exists = Test-Path -LiteralPath $Path
    [ordered]@{
        Path = $Path
        Exists = $exists
        Length = if ($exists) { (Get-Item -LiteralPath $Path).Length } else { 0 }
        SHA256 = if ($exists) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash } else { $null }
        LastWriteTime = if ($exists) { (Get-Item -LiteralPath $Path).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
    }
}

function Get-HttpState {
    param([int]$Port, [string]$CacheBust)
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?t=$CacheBust#overview" -TimeoutSec 60
    $missing = @($requiredMarkers | Where-Object { -not $response.Content.Contains($_) })
    [ordered]@{
        Status = [int]$response.StatusCode
        Length = $response.Content.Length
        MissingMarkers = $missing
        HasAdaptiveFix = $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
        HasFormalHeader = $response.Content.Contains("topbar branded-topbar")
    }
}

if (-not (Test-Path -LiteralPath $stagedPath)) {
    throw "Staged HTML missing: $stagedPath"
}
$stagedHash = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash
if ($stagedHash -ne $expectedHash) {
    throw "Staged SHA256 mismatch: expected=$expectedHash actual=$stagedHash"
}
$stagedText = Get-Content -Raw -LiteralPath $stagedPath -Encoding UTF8
foreach ($marker in $requiredMarkers) {
    if (-not $stagedText.Contains($marker)) {
        throw "Staged HTML missing marker: $marker"
    }
}

$service8093 = Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction Stop
$service8768 = Get-Service -Name "BFV4PreviewWs8768" -ErrorAction Stop
$task8094 = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction Stop
if ($service8093.Status -ne "Running") { throw "BFV4PreviewProxy8093 is not running before deployment" }
if ($service8768.Status -ne "Running") { throw "BFV4PreviewWs8768 is not running before deployment" }
foreach ($port in 8093, 8094, 8768) {
    if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "Port $port is not listening before deployment"
    }
}

$before = [ordered]@{}
$backups = [ordered]@{}
foreach ($entry in $targets.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $entry.Value)) {
        throw "Target HTML missing: $($entry.Value)"
    }
    $before[$entry.Key] = Get-TargetState -Path $entry.Value
    $backups[$entry.Key] = "$($entry.Value).bak_adaptive_layout_$stamp"
}

$copied = @()
try {
    foreach ($entry in $targets.GetEnumerator()) {
        Copy-Item -LiteralPath $entry.Value -Destination $backups[$entry.Key]
        Copy-Item -LiteralPath $stagedPath -Destination $entry.Value -Force
        $copied += $entry.Key
    }

    $after = [ordered]@{}
    foreach ($entry in $targets.GetEnumerator()) {
        $state = Get-TargetState -Path $entry.Value
        if ($state.SHA256 -ne $stagedHash) {
            throw "$($entry.Key) file hash mismatch after deployment"
        }
        $after[$entry.Key] = $state
    }

    Start-Sleep -Seconds 2
    $http = [ordered]@{
        "8093" = Get-HttpState -Port 8093 -CacheBust "adaptive-$stamp-8093"
        "8094" = Get-HttpState -Port 8094 -CacheBust "adaptive-$stamp-8094"
    }
    foreach ($port in 8093, 8094) {
        if ($http["$port"].Status -ne 200 -or $http["$port"].MissingMarkers.Count -ne 0) {
            throw "HTTP verification failed for port $port"
        }
    }

    [ordered]@{
        DeployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        StagedPath = $stagedPath
        StagedSHA256 = $stagedHash
        Before = $before
        Backups = $backups
        After = $after
        Http = $http
        Runtime = [ordered]@{
            BFV4PreviewProxy8093 = (Get-Service -Name "BFV4PreviewProxy8093").Status.ToString()
            BFV4PreviewWs8768 = (Get-Service -Name "BFV4PreviewWs8768").Status.ToString()
            Preview8094Task = $task8094.State.ToString()
            Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            ServicesRestarted = $false
        }
    } | ConvertTo-Json -Depth 10
}
catch {
    foreach ($key in $copied) {
        if (Test-Path -LiteralPath $backups[$key]) {
            Copy-Item -LiteralPath $backups[$key] -Destination $targets[$key] -Force
        }
    }
    throw
}
