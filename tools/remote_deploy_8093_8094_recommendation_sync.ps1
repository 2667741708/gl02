$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$frontendName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6auY54KJ5YmN56uv5pWw5o2u"))
$engineName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6LCD5o6n57uT6K6655Sf5oiQ5byV5pOO"))
$diagnosisServiceName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6Ieq5Yqo6K+K5pat5pyN5Yqh"))
$temp = "C:\Users\Administrator\AppData\Local\Temp"
$archive = Join-Path $temp "recommendation_sync.zip"
$payload = Join-Path $temp "recommendation_sync_20260806_r2"
$frontend = Join-Path $root $frontendName
$targetEngine = Join-Path $root $engineName
$targetAdapter = Join-Path (Join-Path $root $diagnosisServiceName) "recommendation_adapter.py"
$targetBridge = Join-Path (Join-Path $root $diagnosisServiceName) "local_pg_ws_bridge.py"
$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$service8768 = "BFV4PreviewWs8768"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8093_8094_recommendation_sync_20260806\$stamp"
$stage = Join-Path $root ".deploy_staging\recommendation_sync_$stamp"
$python = "C:\Program Files\Python311\python.exe"
$serviceStopped = $false
$mutationStarted = $false
$success = $false

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = $null -ne (Get-ListenerPid $Port)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Install-FileAtomic([string]$Source, [string]$Target) {
    $temporary = "$Target.recommendation_sync.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Invoke-Http([string]$Uri) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 30 }
        catch {
            $lastError = $_
            if ($attempt -lt 8) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

if (Test-Path -LiteralPath $payload) { throw "Temporary payload already exists: $payload" }
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Deployment archive is missing" }
if ((Get-Service -Name $service8768 -ErrorAction Stop).Status -ne "Running") { throw "8768 service is not running" }
$pid8093Before = Get-ListenerPid 8093
$pid8094Before = Get-ListenerPid 8094
$pid8768Before = Get-ListenerPid 8768
$pid8770Before = Get-ListenerPid 8770
$pid11434Before = Get-ListenerPid 11434
if (-not $pid8093Before -or -not $pid8094Before -or -not $pid8768Before) {
    throw "8093/8094/8768 must be listening before deployment"
}

Expand-Archive -LiteralPath $archive -DestinationPath $payload -Force
$manifestPath = Join-Path $payload "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Manifest is missing" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne "recommendation_sync_manifest.v1") { throw "Unexpected manifest schema" }
foreach ($property in $manifest.files.PSObject.Properties) {
    $path = Join-Path $payload ($property.Name.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Payload file missing: $($property.Name)" }
    if ((Get-Sha256 $path) -ne $property.Value.sha256) { throw "Payload hash mismatch: $($property.Name)" }
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -LiteralPath $targetEngine -Destination (Join-Path $backup $engineName) -Recurse -Force
Copy-Item -LiteralPath $targetAdapter -Destination (Join-Path $backup "recommendation_adapter.py") -Force
Copy-Item -LiteralPath $targetBridge -Destination (Join-Path $backup "local_pg_ws_bridge.py") -Force
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup "frontend_dashboard_v3.server.html") -Force
Copy-Item -LiteralPath $page8094 -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force

try {
    $stageEngine = Join-Path $stage $engineName
    Copy-Item -LiteralPath (Join-Path (Join-Path $payload "runtime") $engineName) -Destination $stageEngine -Recurse -Force
    $stageAdapter = Join-Path $stage "recommendation_adapter.py"
    $stageBridge = Join-Path $stage "local_pg_ws_bridge.py"
    $stage8093 = Join-Path $stage "frontend_dashboard_v3.server.html"
    $stage8094 = Join-Path $stage "frontend_dashboard_v3.8094_preview.server.html"
    $payloadDiagnosis = Join-Path (Join-Path $payload "runtime") $diagnosisServiceName
    Copy-Item -LiteralPath (Join-Path $payloadDiagnosis "recommendation_adapter.py") -Destination $stageAdapter -Force
    Copy-Item -LiteralPath (Join-Path $payloadDiagnosis "local_pg_ws_bridge.py") -Destination $stageBridge -Force
    Copy-Item -LiteralPath (Join-Path $payload "source\frontend_dashboard_v3.server.html") -Destination $stage8093 -Force
    Copy-Item -LiteralPath $page8094 -Destination $stage8094 -Force
    & $python -X utf8 (Join-Path $payload "tools\patch_8094_multi_condition_review.py") --target $stage8094 --feature-source $stage8093 --ws-port 8768
    if ($LASTEXITCODE -ne 0) { throw "8094 multi-condition page patch failed" }

    $pythonFiles = @(Get-ChildItem -LiteralPath $stageEngine -Recurse -Filter "*.py" -File).FullName
    $pythonFiles += $stageAdapter
    $pythonFiles += $stageBridge
    & $python -X utf8 -m py_compile @pythonFiles
    if ($LASTEXITCODE -ne 0) { throw "Python compile validation failed" }
    & $python -X utf8 (Join-Path $payload "tools\verify_8094_multi_condition_package.py") --preview-root $stage --engine-dir $stageEngine
    if ($LASTEXITCODE -ne 0) { throw "Recommendation package contract validation failed" }

    Stop-Service -Name $service8768 -Force
    $serviceStopped = $true
    Wait-Port 8768 $false 90
    $mutationStarted = $true

    Remove-Item -LiteralPath $targetEngine -Recurse -Force
    Move-Item -LiteralPath $stageEngine -Destination $targetEngine
    Install-FileAtomic $stageAdapter $targetAdapter
    Install-FileAtomic $stageBridge $targetBridge
    Install-FileAtomic $stage8093 $page8093
    Install-FileAtomic $stage8094 $page8094

    Start-Service -Name $service8768
    $serviceStopped = $false
    Wait-Port 8768 $true 150
    & $python -X utf8 (Join-Path $payload "tools\verify_8094_multi_condition_runtime.py") --uri "ws://127.0.0.1:8768" --timeout 120
    if ($LASTEXITCODE -ne 0) { throw "8768 recommendation runtime validation failed" }

    $http8093 = Invoke-Http "http://127.0.0.1:8093/?recommendation_sync=$stamp#optimization"
    $http8094 = Invoke-Http "http://127.0.0.1:8094/?recommendation_sync=$stamp#optimization"
    foreach ($response in @($http8093, $http8094)) {
        if ($response.StatusCode -ne 200) { throw "Recommendation page HTTP status is not 200" }
        if (-not $response.Content.Contains("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805")) { throw "Multi-condition page marker is missing" }
        if (-not $response.Content.Contains("get('ws_port') || '8768'")) { throw "Page does not use shared 8768" }
    }

    foreach ($property in $manifest.files.PSObject.Properties) {
        $relative = $property.Name
        if (-not $relative.StartsWith("runtime/")) { continue }
        $targetRelative = $relative.Substring("runtime/".Length).Replace("/", "\")
        $target = Join-Path $root $targetRelative
        if ((Get-Sha256 $target) -ne $property.Value.sha256) { throw "Installed hash mismatch: $targetRelative" }
    }
    if ((Get-Sha256 $page8093) -ne (Get-Sha256 (Join-Path $payload "source\frontend_dashboard_v3.server.html"))) {
        throw "8093 page does not match the latest local source"
    }

    $success = $true
    [ordered]@{
        ok = $true
        operation = $manifest.operation
        deployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        backup = $backup
        engineVersion = $manifest.engine_version
        manifestFileCount = @($manifest.files.PSObject.Properties).Count
        sharedWsPort = 8768
        pid8768Before = $pid8768Before
        pid8768After = Get-ListenerPid 8768
        pid8093ObservedBefore = $pid8093Before
        pid8093ObservedAfter = Get-ListenerPid 8093
        pid8094ObservedBefore = $pid8094Before
        pid8094ObservedAfter = Get-ListenerPid 8094
        pid8770Unchanged = ((Get-ListenerPid 8770) -eq $pid8770Before)
        pid11434Unchanged = ((Get-ListenerPid 11434) -eq $pid11434Before)
        http8093 = [int]$http8093.StatusCode
        http8094 = [int]$http8094.StatusCode
        page8093Sha256 = Get-Sha256 $page8093
        page8094Sha256 = Get-Sha256 $page8094
        engineCoreSha256 = Get-Sha256 (Join-Path $targetEngine "recommendation\core.py")
        enginePolicySha256 = Get-Sha256 (Join-Path $targetEngine "policy\three_rules_two_systems.yaml")
        adapterSha256 = Get-Sha256 $targetAdapter
        bridgeSha256 = Get-Sha256 $targetBridge
    } | ConvertTo-Json -Depth 6
}
catch {
    $failure = $_
    if ($mutationStarted) {
        Stop-Service -Name $service8768 -Force -ErrorAction SilentlyContinue
        Wait-Port 8768 $false 60
        Remove-Item -LiteralPath $targetEngine -Recurse -Force -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath (Join-Path $backup $engineName) -Destination $targetEngine -Recurse -Force
        Install-FileAtomic (Join-Path $backup "recommendation_adapter.py") $targetAdapter
        Install-FileAtomic (Join-Path $backup "local_pg_ws_bridge.py") $targetBridge
        Install-FileAtomic (Join-Path $backup "frontend_dashboard_v3.server.html") $page8093
        Install-FileAtomic (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") $page8094
    }
    if ((Get-Service -Name $service8768 -ErrorAction SilentlyContinue).Status -ne "Running") {
        Start-Service -Name $service8768 -ErrorAction SilentlyContinue
        Wait-Port 8768 $true 150
    }
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
    if (-not $success) { Write-Warning "Recommendation sync failed; rollback was attempted from $backup" }
}
