$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = (Get-Location).Path
$serviceName = "BFV4PreviewProxy8093"
$htmlPath = (Get-ChildItem -LiteralPath $root -Directory |
    ForEach-Object { Join-Path $_.FullName "frontend_dashboard_v3.server.html" } |
    Where-Object { Test-Path -LiteralPath $_ } |
    Select-Object -First 1)
$stagedPath = Join-Path $root "logs\frontend_dashboard_v3.core_metric_clip_fix.staged.html"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$htmlPath.bak_core_metric_clip_$stamp"
$serviceWasStopped = $false

function Wait-Port {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Ensure-ProxyRunning {
    $service = Get-Service -Name $serviceName
    if ($service.Status -ne "Running") {
        Start-Service -Name $serviceName
    }
    Wait-Port -Port 8093 -Listening $true
}

if (-not (Test-Path -LiteralPath $htmlPath)) { throw "Target HTML missing: $htmlPath" }
if (-not (Test-Path -LiteralPath $stagedPath)) { throw "Staged HTML missing: $stagedPath" }

$required = @(
    "BUG-8093-CORE-METRIC-GROUP-CLIP-20260715",
    "flex:calc(var(--rows) + 1) 1 0!important",
    "repeat(var(--rows),minmax(22px,1fr))",
    "BFCoreMetricRowsV7",
    "CORE_METRIC_PAGES_V7",
    "REQ-8093-CORE-SPARK-DETAIL-CORRELATION-20260715",
    "REQ-8093-THERMAL-DIAGNOSIS-DISPLAY-20260716",
    "THERMAL_DIAGNOSIS_DISPLAY",
    "core-detail-dialog",
    "corePearsonV1",
    "topbar branded-topbar"
)
$stagedText = Get-Content -LiteralPath $stagedPath -Raw -Encoding UTF8
foreach ($marker in $required) {
    if (-not $stagedText.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}

$before = [pscustomobject]@{
    Service = (Get-Service -Name $serviceName).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    FileHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
    StagedHash = (Get-FileHash -LiteralPath $stagedPath -Algorithm SHA256).Hash
}
if (-not $before.Port8768) { throw "8768 data bridge is not listening before deployment" }

try {
    Stop-Service -Name $serviceName -Force
    $serviceWasStopped = $true
    Wait-Port -Port 8093 -Listening $false
    if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8768 data bridge stopped unexpectedly; refusing replacement"
    }

    Copy-Item -LiteralPath $htmlPath -Destination $backupPath
    Copy-Item -LiteralPath $stagedPath -Destination $htmlPath -Force
    Start-Service -Name $serviceName
    $serviceWasStopped = $false
    Wait-Port -Port 8093 -Listening $true
    Start-Sleep -Seconds 4

    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?t=$stamp#overview" -UseBasicParsing -TimeoutSec 45
    $httpText = $response.Content
    foreach ($marker in $required) {
        if (-not $httpText.Contains($marker)) { throw "HTTP response missing marker: $marker" }
    }
    $fileHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
    if ($fileHash -ne $before.StagedHash) { throw "Deployed file hash does not match staged file hash" }

    [pscustomobject]@{
        Before = $before
        BackupPath = $backupPath
        AfterService = (Get-Service -Name $serviceName).Status.ToString()
        Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        FileHash = $fileHash
        HttpStatus = [int]$response.StatusCode
        RequiredMarkers = $required.Count
        HasClipFix = $httpText.Contains("BUG-8093-CORE-METRIC-GROUP-CLIP-20260715")
        HasFormalHeader = $httpText.Contains("topbar branded-topbar")
    } | ConvertTo-Json -Depth 4
}
catch {
    if ($serviceWasStopped -or (Get-Service -Name $serviceName).Status -ne "Running") {
        Ensure-ProxyRunning
    }
    throw
}
