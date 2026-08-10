param(
    [string]$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW",
    [string]$PatcherPath = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# OPS-8093-QA-FETCH-RESILIENCE-20260806
$page8093 = Join-Path $ProjectRoot "高炉前端数据\frontend_dashboard_v3.server.html"
$page8094 = Join-Path $ProjectRoot "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$configPath = Join-Path $ProjectRoot "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$proxyPath = Join-Path $ProjectRoot "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$python = "C:\Program Files\Python311\python.exe"
$packagePatcher = Join-Path $PSScriptRoot "patch_8093_assistant_fetch_resilience.py"
$patcher = if ([string]::IsNullOrWhiteSpace($PatcherPath)) { $packagePatcher } else { $PatcherPath }
$marker = "OPS-8093-QA-FETCH-RESILIENCE-20260806"
$expectedPageHashes = @(
    "4C552CBA92D70379E3CBFD6447195F6B1105403009D3C6B39512BF5EF5D31262"
)
$targetPorts = @(8093, 8094, 8768, 8770, 11434)
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $ProjectRoot "logs\deploy_backups\8093_fetch_resilience_$stamp"
$candidate = Join-Path $ProjectRoot ".deploy_staging\frontend_dashboard_v3.server.fetch_$stamp.html"
$mutex = [Threading.Mutex]::new($false, "Global\BFV4PreviewProxy8093Deployment")
$lockTaken = $false
$installed = $false
$originalBackup = Join-Path $backupRoot "frontend_dashboard_v3.server.html"

function Get-ListenerSnapshot {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $targetPorts -contains [int]$_.LocalPort })
}

function Get-ListenerRow {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)]$Snapshot
    )

    $row = @($Snapshot | Where-Object { [int]$_.LocalPort -eq $Port }) | Select-Object -First 1
    if ($null -eq $row) { throw "protected listener is missing: $Port" }
    return [ordered]@{ port = $Port; pid = [int]$row.OwningProcess }
}

function Get-ProtectedListeners {
    $snapshot = Get-ListenerSnapshot
    $rows = [ordered]@{}
    foreach ($port in $targetPorts) { $rows[[string]$port] = Get-ListenerRow -Port $port -Snapshot $snapshot }
    return $rows
}

function Wait-Page {
    param([int]$TimeoutSeconds = 45)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/frontend_dashboard_v3.server.html?t=$stamp" -TimeoutSec 10
            if ($response.StatusCode -eq 200 -and ([string]$response.Content).Contains($marker)) { return $response }
        } catch { }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "8093 page did not expose the fetch resilience marker"
}

foreach ($path in @($page8093, $page8094, $configPath, $proxyPath, $python, $patcher)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "required file is missing: $path" }
}

try {
    $lockTaken = $mutex.WaitOne([TimeSpan]::FromMinutes(2))
    if (-not $lockTaken) { throw "another 8093 deployment owns the global deployment lock" }

    $listenersBefore = Get-ProtectedListeners
    $service = Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction Stop
    if ($service.Status.ToString() -ne "Running") { throw "8093 service must be Running for hot deployment" }

    $pageHashBefore = (Get-FileHash -LiteralPath $page8093 -Algorithm SHA256).Hash
    if ($expectedPageHashes -notcontains $pageHashBefore) { throw "8093 page hash is outside the approved baseline: $pageHashBefore" }
    $protectedHashesBefore = [ordered]@{
        page8094 = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
        config = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        proxy = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
    }

    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $candidate) -Force | Out-Null
    Copy-Item -LiteralPath $page8093 -Destination $originalBackup
    Copy-Item -LiteralPath $page8093 -Destination $candidate -Force

    $patchJson = & $python -X utf8 $patcher --target $candidate
    if ($LASTEXITCODE -ne 0) { throw "fetch resilience patch failed: $LASTEXITCODE" }
    $patchResult = $patchJson | ConvertFrom-Json
    if (-not (Select-String -LiteralPath $candidate -SimpleMatch $marker -Quiet)) { throw "candidate marker is missing" }

    $replaceBackup = Join-Path $backupRoot "frontend_dashboard_v3.server.replace.bak"
    [IO.File]::Replace($candidate, $page8093, $replaceBackup, $true)
    $installed = $true
    $response = Wait-Page

    $listenersAfter = Get-ProtectedListeners
    foreach ($port in $targetPorts) {
        if ($listenersAfter[[string]$port].pid -ne $listenersBefore[[string]$port].pid) {
            throw "protected listener changed during hot deployment: $port"
        }
    }
    $protectedHashesAfter = [ordered]@{
        page8094 = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
        config = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        proxy = (Get-FileHash -LiteralPath $proxyPath -Algorithm SHA256).Hash
    }
    foreach ($name in $protectedHashesBefore.Keys) {
        if ($protectedHashesAfter[$name] -ne $protectedHashesBefore[$name]) { throw "protected hash changed: $name" }
    }

    $result = [ordered]@{
        schema = "ops.8093.qa-fetch-resilience.hot-deploy.v1"
        requirement_id = "OPS-8093-QA-FETCH-RESILIENCE-20260806"
        completed_at = (Get-Date).ToString("o")
        backup_root = $backupRoot
        patch = $patchResult
        page_sha256_before = $pageHashBefore
        page_sha256_after = (Get-FileHash -LiteralPath $page8093 -Algorithm SHA256).Hash
        listeners_before = @($listenersBefore.Values)
        listeners_after = @($listenersAfter.Values)
        protected_hashes_unchanged = $true
        http_status = [int]$response.StatusCode
        marker_present = ([string]$response.Content).Contains($marker)
    }
    $result | ConvertTo-Json -Depth 12
} catch {
    if ($installed -and (Test-Path -LiteralPath $originalBackup -PathType Leaf)) {
        Copy-Item -LiteralPath $originalBackup -Destination $page8093 -Force
    }
    throw
} finally {
    Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
    if ($lockTaken) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
