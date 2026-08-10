$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$frontendName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6auY54KJ5YmN56uv5pWw5o2u"))
$temp = "C:\Users\Administrator\AppData\Local\Temp"
$archive = Join-Path $temp "recommendation_visual_frontend.zip"
$payload = Join-Path $temp "recommendation_visual_frontend_20260806_r2"
$frontend = Join-Path $root $frontendName
$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$python = "C:\Program Files\Python311\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8093_8094_recommendation_visual_20260806\$stamp"
$stage = Join-Path $root ".deploy_staging\recommendation_visual_$stamp"
$visualMarker = "REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806"
$confidenceRemovalMarker = "REQ-UI-REMOVE-JUDGMENT-CONFIDENCE-20260806"
$installed8094 = $false
$installed8093 = $false
$success = $false

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Install-FileAtomic([string]$Source, [string]$Target) {
    $temporary = "$Target.recommendation_visual.tmp"
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Invoke-Http([string]$Uri) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 30 }
        catch {
            $lastError = $_
            if ($attempt -lt 6) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

function Assert-VisualPage([Microsoft.PowerShell.Commands.BasicHtmlWebResponseObject]$Response, [string]$PortLabel) {
    if ($Response.StatusCode -ne 200) { throw "$PortLabel HTTP status is not 200" }
    $content = [string]$Response.Content
    foreach ($marker in @(
        $visualMarker,
        $confidenceRemovalMarker,
        "OptimizationTab = OptimizationVisualWorkbenchLayout;",
        "BF_CORE_EVIDENCE_IDS_V2",
        "data-core-evidence-count",
        "get('ws_port') || '8768'"
    )) {
        if (-not $content.Contains($marker)) { throw "$PortLabel page marker missing: $marker" }
    }
    if ($content.Contains("判断把握")) { throw "$PortLabel still exposes judgment-confidence copy" }
}

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Deployment archive is missing" }
if (Test-Path -LiteralPath $payload) { throw "Temporary payload already exists: $payload" }
$pid8093Before = Get-ListenerPid 8093
$pid8094Before = Get-ListenerPid 8094
$pid8768Before = Get-ListenerPid 8768
$pid8770Before = Get-ListenerPid 8770
$pid11434Before = Get-ListenerPid 11434
if (-not $pid8093Before -or -not $pid8094Before -or -not $pid8768Before -or -not $pid8770Before -or -not $pid11434Before) {
    throw "8093/8094/8768/8770/11434 must all be listening before frontend deployment"
}

Expand-Archive -LiteralPath $archive -DestinationPath $payload -Force
$manifestPath = Join-Path $payload "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Manifest is missing" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne "recommendation_visual_frontend_manifest.v1") { throw "Unexpected manifest schema" }
if ($manifest.shared_ws_port -ne 8768 -or $manifest.service_restart_required -ne $false) { throw "Unsafe frontend manifest contract" }
if ($manifest.core_evidence_count -ne 19) { throw "Unexpected core evidence count" }
if ($manifest.judgment_confidence_visible -ne $false) { throw "Unsafe judgment-confidence display contract" }
foreach ($property in $manifest.files.PSObject.Properties) {
    $path = Join-Path $payload ($property.Name.Replace("/", "\"))
    if ((Get-Sha256 $path) -ne $property.Value.sha256) { throw "Payload hash mismatch: $($property.Name)" }
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup "frontend_dashboard_v3.server.html") -Force
Copy-Item -LiteralPath $page8094 -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force

try {
    $stage8093 = Join-Path $stage "frontend_dashboard_v3.server.html"
    $stage8094 = Join-Path $stage "frontend_dashboard_v3.8094_preview.server.html"
    Copy-Item -LiteralPath (Join-Path $payload "source\frontend_dashboard_v3.server.html") -Destination $stage8093 -Force
    Copy-Item -LiteralPath $page8094 -Destination $stage8094 -Force
    & $python -X utf8 (Join-Path $payload "tools\patch_8094_multi_condition_review.py") --target $stage8094 --feature-source $stage8093 --ws-port 8768
    if ($LASTEXITCODE -ne 0) { throw "8094 visual workbench patch failed" }
    & $python -X utf8 (Join-Path $payload "tools\patch_remove_judgment_confidence.py") --target $stage8093
    if ($LASTEXITCODE -ne 0) { throw "8093 judgment-confidence removal failed" }
    & $python -X utf8 (Join-Path $payload "tools\patch_remove_judgment_confidence.py") --target $stage8094
    if ($LASTEXITCODE -ne 0) { throw "8094 judgment-confidence removal failed" }

    $sourceText = Get-Content -LiteralPath $stage8093 -Raw -Encoding UTF8
    $previewText = Get-Content -LiteralPath $stage8094 -Raw -Encoding UTF8
    foreach ($text in @($sourceText, $previewText)) {
        if ($text.Count -eq 0 -or -not $text.Contains($visualMarker)) { throw "Staged visual page is incomplete" }
        if (-not $text.Contains("OptimizationTab = OptimizationVisualWorkbenchLayout;")) { throw "Staged visual workbench assignment is missing" }
        if (-not $text.Contains("get('ws_port') || '8768'")) { throw "Staged page does not use shared 8768" }
        if (-not $text.Contains($confidenceRemovalMarker)) { throw "Staged page lacks the confidence-removal marker" }
        if ($text.Contains("判断把握")) { throw "Staged page still contains judgment-confidence copy" }
    }

    Install-FileAtomic $stage8094 $page8094
    $installed8094 = $true
    $http8094 = Invoke-Http "http://127.0.0.1:8094/?recommendation_visual=$stamp#optimization"
    Assert-VisualPage $http8094 "8094"

    Install-FileAtomic $stage8093 $page8093
    $installed8093 = $true
    $http8093 = Invoke-Http "http://127.0.0.1:8093/?recommendation_visual=$stamp#optimization"
    Assert-VisualPage $http8093 "8093"

    $pid8093After = Get-ListenerPid 8093
    $pid8094After = Get-ListenerPid 8094
    $pid8768After = Get-ListenerPid 8768
    $pid8770After = Get-ListenerPid 8770
    $pid11434After = Get-ListenerPid 11434
    if ($pid8093After -ne $pid8093Before -or $pid8094After -ne $pid8094Before -or $pid8768After -ne $pid8768Before -or $pid8770After -ne $pid8770Before -or $pid11434After -ne $pid11434Before) {
        throw "A protected service PID changed during frontend-only deployment"
    }
    $sourcePageHash = $manifest.files.'source/frontend_dashboard_v3.server.html'.sha256
    if ((Get-Sha256 $page8093) -ne $sourcePageHash) { throw "8093 page does not match the latest local source" }
    if ((Get-Sha256 $page8094) -ne (Get-Sha256 $stage8094)) { throw "8094 installed hash mismatch" }

    $success = $true
    [ordered]@{
        ok = $true
        operation = $manifest.operation
        deployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        backup = $backup
        serviceRestarted = $false
        sharedWsPort = 8768
        http8093 = [int]$http8093.StatusCode
        http8094 = [int]$http8094.StatusCode
        pid8093Unchanged = ($pid8093After -eq $pid8093Before)
        pid8094Unchanged = ($pid8094After -eq $pid8094Before)
        pid8768Unchanged = ($pid8768After -eq $pid8768Before)
        pid8770Unchanged = ($pid8770After -eq $pid8770Before)
        pid11434Unchanged = ($pid11434After -eq $pid11434Before)
        page8093Sha256 = Get-Sha256 $page8093
        page8094Sha256 = Get-Sha256 $page8094
        coreEvidenceCount = 19
        judgmentConfidenceVisible = $false
    } | ConvertTo-Json -Depth 6
}
catch {
    $failure = $_
    if ($installed8093) { Install-FileAtomic (Join-Path $backup "frontend_dashboard_v3.server.html") $page8093 }
    if ($installed8094) { Install-FileAtomic (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") $page8094 }
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
    if (-not $success) { Write-Warning "Frontend visual deployment failed; installed pages were rolled back from $backup" }
}
