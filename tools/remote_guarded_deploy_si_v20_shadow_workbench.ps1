$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$backend = Join-Path $frontend "智能助手\backend"
$assets = Join-Path $frontend "assets"
$server = Join-Path $backend "ollama_proxy_server.py"
$heatModule = Join-Path $backend "heat_performance_quality.py"
$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$pageStandalone = Join-Path $frontend "si_v20_workbench.html"
$module = Join-Path $backend "si_v20_shadow.py"
$model = Join-Path $backend "models\si_v20_history_portable_v1.json.gz"
$modelAudit = Join-Path $backend "models\si_v20_history_portable_v1.json.gz.audit.json"
$asset = Join-Path $assets "bf-si-v20-shadow-workbench.js"
$assetStandalone = Join-Path $assets "bf-si-v20-workbench.js"

$tempRoot = "C:\Users\Administrator\AppData\Local\Temp"
$uploadedPatcher = Join-Path $tempRoot "patch_si_v20_shadow_workbench_surfaces.py"
$uploadedModule = Join-Path $tempRoot "si_v20_shadow.py"
$uploadedModel = Join-Path $tempRoot "si_v20_history_portable_v1.json.gz"
$uploadedModelAudit = Join-Path $tempRoot "si_v20_history_portable_v1.json.gz.audit.json"
$uploadedAsset = Join-Path $tempRoot "bf-si-v20-shadow-workbench.js"
$uploadedStandalonePage = Join-Path $tempRoot "si_v20_workbench.html"
$uploadedStandaloneAsset = Join-Path $tempRoot "bf-si-v20-workbench.js"

$manager = Join-Path $root "tools\manage_22012_managed_services.ps1"
$guardConfig = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$restart8094 = Join-Path $root "tools\restart_22012_8094_preview.ps1"
$python = "C:\Program Files\Python311\python.exe"
$service8093 = "BFV4PreviewProxy8093"
$marker = "REQ-SI-V20-8093-8094-SHADOW-WORKBENCH-20260808"
$assetName = "bf-si-v20-shadow-workbench.js"
$expectedModelHash = "FD31DB24EF9B4E9C81BAAE81A46693E5B9F2E539DBEC9C2B75AE95946055FC8C"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\si_v20_shadow_20260808\$stamp"
$stage = Join-Path $tempRoot "si_v20_shadow_stage_$stamp"
$stageBackend = Join-Path $stage "backend"
$stageModels = Join-Path $stageBackend "models"
$stageServer = Join-Path $stageBackend "ollama_proxy_server.py"
$stageHeatModule = Join-Path $stageBackend "heat_performance_quality.py"
$stageModule = Join-Path $stageBackend "si_v20_shadow.py"
$stageModel = Join-Path $stageModels "si_v20_history_portable_v1.json.gz"
$stagePage8093 = Join-Path $stage "frontend8093.html"
$stagePage8094 = Join-Path $stage "frontend8094.html"
$stageStandalonePage = Join-Path $stage "si_v20_workbench.html"

function Wait-ServiceState {
    param([string]$Name, [string]$State, [int]$TimeoutSeconds = 45)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $State) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $State"
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 90)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}

function Install-AtomicFile {
    param([string]$Source, [string]$Target)
    $directory = Split-Path -Parent $Target
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = "$Target.si_v20_installing"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Backup-IfPresent {
    param([string]$Source, [string]$Name)
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        Copy-Item -LiteralPath $Source -Destination (Join-Path $backup $Name) -Force
        return $true
    }
    return $false
}

function Restore-IfBackedUp {
    param([string]$Name, [string]$Target)
    $saved = Join-Path $backup $Name
    if (Test-Path -LiteralPath $saved -PathType Leaf) {
        Install-AtomicFile -Source $saved -Target $Target
    }
}

function Invoke-JsonGet {
    param([string]$Uri)
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 60
    if ($response.StatusCode -ne 200) { throw "$Uri returned HTTP $($response.StatusCode)" }
    return ($response.Content | ConvertFrom-Json)
}

function Invoke-WebGetWithRetry {
    param([string]$Uri, [int]$Attempts = 8)
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 60 }
        catch {
            $lastError = $_
            if ($attempt -lt $Attempts) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

$required = @(
    $server, $heatModule, $page8093, $page8094, $manager, $guardConfig,
    $restart8094, $python, $uploadedPatcher, $uploadedModule, $uploadedModel,
    $uploadedModelAudit, $uploadedAsset,
    $uploadedStandalonePage, $uploadedStandaloneAsset
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "required file missing: $path" }
}

$modelHash = (Get-FileHash -LiteralPath $uploadedModel -Algorithm SHA256).Hash
if ($modelHash -ne $expectedModelHash) { throw "portable model hash mismatch: $modelHash" }
$expectedAssetHash = (Get-FileHash -LiteralPath $uploadedAsset -Algorithm SHA256).Hash

$serviceBefore = Get-Service -Name $service8093 -ErrorAction Stop
$taskBefore = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne "Running" -or $taskBefore.State.ToString() -ne "Running") {
    throw "8093 guard and 8094 preview task must both be running"
}
$listenersBefore = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $listenersBefore["$port"] = [int]$listener.OwningProcess
}

New-Item -ItemType Directory -Path $stageModels -Force | Out-Null
Copy-Item -LiteralPath $server -Destination $stageServer -Force
Copy-Item -LiteralPath $heatModule -Destination $stageHeatModule -Force
Copy-Item -LiteralPath $page8093 -Destination $stagePage8093 -Force
Copy-Item -LiteralPath $page8094 -Destination $stagePage8094 -Force
Copy-Item -LiteralPath $uploadedStandalonePage -Destination $stageStandalonePage -Force
Copy-Item -LiteralPath $uploadedModule -Destination $stageModule -Force
Copy-Item -LiteralPath $uploadedModel -Destination $stageModel -Force

& $python -X utf8 $uploadedPatcher --server $stageServer --page8093 $stagePage8093 --page8094 $stagePage8094
if ($LASTEXITCODE -ne 0) { throw "surface patcher failed" }
& $python -X utf8 -m py_compile $stageServer $stageModule
if ($LASTEXITCODE -ne 0) { throw "staged Python syntax check failed" }

$stageServerText = Get-Content -LiteralPath $stageServer -Raw -Encoding UTF8
$stage8093Text = Get-Content -LiteralPath $stagePage8093 -Raw -Encoding UTF8
$stage8094Text = Get-Content -LiteralPath $stagePage8094 -Raw -Encoding UTF8
if (-not $stageServerText.Contains($marker)) { throw "staged server marker missing" }
if (-not $stage8093Text.Contains($assetName)) { throw "staged 8093 asset tag missing" }
if (-not $stage8094Text.Contains($assetName)) { throw "staged 8094 asset tag missing" }
if (-not (Get-Content -LiteralPath $stageStandalonePage -Raw -Encoding UTF8).Contains('bf-si-v20-workbench.js')) { throw "staged standalone page asset tag missing" }

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
$env:BF_SI_V20_MODEL_PATH = $stageModel
& $python -X utf8 $stageModule --ensure-schema
if ($LASTEXITCODE -ne 0) { throw "V20 prediction audit migration/status check failed" }

New-Item -ItemType Directory -Path $backup -Force | Out-Null
$null = Backup-IfPresent -Source $server -Name "ollama_proxy_server.py"
$null = Backup-IfPresent -Source $page8093 -Name "frontend_dashboard_v3.server.html"
$null = Backup-IfPresent -Source $page8094 -Name "frontend_dashboard_v3.8094_preview.server.html"
$moduleExisted = Backup-IfPresent -Source $module -Name "si_v20_shadow.py"
$modelExisted = Backup-IfPresent -Source $model -Name "si_v20_history_portable_v1.json.gz"
$modelAuditExisted = Backup-IfPresent -Source $modelAudit -Name "si_v20_history_portable_v1.json.gz.audit.json"
$assetExisted = Backup-IfPresent -Source $asset -Name "bf-si-v20-shadow-workbench.js"
$standalonePageExisted = Backup-IfPresent -Source $pageStandalone -Name "si_v20_workbench.html"
$standaloneAssetExisted = Backup-IfPresent -Source $assetStandalone -Name "bf-si-v20-workbench.js"

$installed = $false
$guardRestored = $false
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState -Name $service8093 -State "Stopped" -TimeoutSeconds 30
    Wait-PortState -Port 8093 -Listening $false -TimeoutSeconds 30

    Install-AtomicFile -Source $stageServer -Target $server
    Install-AtomicFile -Source $stagePage8093 -Target $page8093
    Install-AtomicFile -Source $stagePage8094 -Target $page8094
    Install-AtomicFile -Source $uploadedModule -Target $module
    Install-AtomicFile -Source $uploadedModel -Target $model
    Install-AtomicFile -Source $uploadedModelAudit -Target $modelAudit
    Install-AtomicFile -Source $uploadedAsset -Target $asset
    Install-AtomicFile -Source $uploadedStandalonePage -Target $pageStandalone
    Install-AtomicFile -Source $uploadedStandaloneAsset -Target $assetStandalone
    $installed = $true
}
catch {
    Restore-IfBackedUp -Name "ollama_proxy_server.py" -Target $server
    Restore-IfBackedUp -Name "frontend_dashboard_v3.server.html" -Target $page8093
    Restore-IfBackedUp -Name "frontend_dashboard_v3.8094_preview.server.html" -Target $page8094
    if ($moduleExisted) { Restore-IfBackedUp -Name "si_v20_shadow.py" -Target $module }
    if ($modelExisted) { Restore-IfBackedUp -Name "si_v20_history_portable_v1.json.gz" -Target $model }
    if ($modelAuditExisted) { Restore-IfBackedUp -Name "si_v20_history_portable_v1.json.gz.audit.json" -Target $modelAudit }
    if ($assetExisted) { Restore-IfBackedUp -Name "bf-si-v20-shadow-workbench.js" -Target $asset }
    if ($standalonePageExisted) { Restore-IfBackedUp -Name "si_v20_workbench.html" -Target $pageStandalone }
    if ($standaloneAssetExisted) { Restore-IfBackedUp -Name "bf-si-v20-workbench.js" -Target $assetStandalone }
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState -Name $service8093 -State "Running" -TimeoutSeconds 45
    Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 90
    $guardRestored = $true
}

try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    if ($LASTEXITCODE -ne 0) { throw "8094 managed restart failed" }

    $status8093 = Invoke-JsonGet -Uri "http://127.0.0.1:8093/api/si-v20/status?limit=3&deploy=$stamp"
    $status8094 = Invoke-JsonGet -Uri "http://127.0.0.1:8094/api/si-v20/status?limit=3&deploy=$stamp"
    $history8093 = Invoke-JsonGet -Uri "http://127.0.0.1:8093/api/si-v20/history?limit=1&deploy=$stamp"
    $history8094 = Invoke-JsonGet -Uri "http://127.0.0.1:8094/api/si-v20/history?limit=1&deploy=$stamp"
    if (-not $status8093.ok -or -not $status8094.ok) { throw "V20 status API is not healthy on both ports" }
    if (-not $status8093.audit_table_ready -or -not $status8094.audit_table_ready) { throw "V20 audit table is not ready" }
    if (-not $history8093.ok -or -not $history8094.ok) { throw "V20 history API is not healthy on both ports" }

    $pageResponse8093 = Invoke-WebGetWithRetry -Uri "http://127.0.0.1:8093/?si_v20=$stamp"
    $pageResponse8094 = Invoke-WebGetWithRetry -Uri "http://127.0.0.1:8094/?si_v20=$stamp"
    if (-not $pageResponse8093.Content.Contains($assetName) -or -not $pageResponse8094.Content.Contains($assetName)) {
        throw "one of the pages does not serve the V20 workbench asset tag"
    }
    if ((Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash -ne $expectedAssetHash) {
        throw "installed V20 workbench asset hash mismatch"
    }
}
catch {
    Restore-IfBackedUp -Name "ollama_proxy_server.py" -Target $server
    Restore-IfBackedUp -Name "frontend_dashboard_v3.server.html" -Target $page8093
    Restore-IfBackedUp -Name "frontend_dashboard_v3.8094_preview.server.html" -Target $page8094
    if ($moduleExisted) { Restore-IfBackedUp -Name "si_v20_shadow.py" -Target $module }
    if ($modelExisted) { Restore-IfBackedUp -Name "si_v20_history_portable_v1.json.gz" -Target $model }
    if ($modelAuditExisted) { Restore-IfBackedUp -Name "si_v20_history_portable_v1.json.gz.audit.json" -Target $modelAudit }
    if ($assetExisted) { Restore-IfBackedUp -Name "bf-si-v20-shadow-workbench.js" -Target $asset }
    if ($standalonePageExisted) { Restore-IfBackedUp -Name "si_v20_workbench.html" -Target $pageStandalone }
    if ($standaloneAssetExisted) { Restore-IfBackedUp -Name "bf-si-v20-workbench.js" -Target $assetStandalone }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action restart -ConfigPath $guardConfig | Out-Null
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094 | Out-Null
    throw
}

$listenersAfter = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $listenersAfter["$port"] = [int]$listener.OwningProcess
}
foreach ($port in 8768, 8770, 11434) {
    if ($listenersAfter["$port"] -ne $listenersBefore["$port"]) { throw "protected port $port changed PID" }
}

[ordered]@{
    schema = "ops.si-v20-shadow-workbench.deploy.v1"
    requirement = $marker
    deployed_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    backup = $backup
    staged = $stage
    installed = $installed
    guard_restored = $guardRestored
    model_sha256 = $expectedModelHash
    status_8093 = $status8093
    status_8094 = $status8094
    history_8093_ok = [bool]$history8093.ok
    history_8094_ok = [bool]$history8094.ok
    listeners_before = $listenersBefore
    listeners_after = $listenersAfter
    protected_pids_unchanged = $true
    server_sha256 = (Get-FileHash -LiteralPath $server -Algorithm SHA256).Hash
    page_8093_sha256 = (Get-FileHash -LiteralPath $page8093 -Algorithm SHA256).Hash
    page_8094_sha256 = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 8
