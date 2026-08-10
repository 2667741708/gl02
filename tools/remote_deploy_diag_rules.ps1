param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$startedAt = Get-Date

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$config8093 = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'V3AutoPreviewProxy8094'
$python = 'C:\Program Files\Python311\python.exe'
$deploymentMutex = [Threading.Mutex]::new($false, 'Global\BFDiagnosisRulesDeployment')
$lockTaken = $false
$guardPaused = $false
$guardRestored = $false
$filesApplied = $false
$rollbackApplied = $false

$allowedTargets = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\diag_ai_evidence.py',
    '高炉前端数据\智能助手\backend\diagnosis_model_review.py',
    '高炉前端数据\智能助手\backend\diagnosis_ai_analysis_api.py',
    '高炉前端数据\智能助手\backend\diagnosis_review.py',
    '高炉前端数据\assets\bf-diagnosis-manual-score-local.js',
    '高炉前端数据\assets\bf-diagnosis-manual-score-local.css',
    '高炉前端数据\assets\bf-diagnosis-review-local.js',
    '高炉前端数据\assets\bf-diagnosis-review-local.css'
)

function Get-ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (($null -ne (Get-ListenerPid $Port)) -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}

function Invoke-8093Manager([string]$Action) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action $Action -ConfigPath $config8093 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "8093 manager action failed: $Action" }
}

function Install-Atomically([string]$Source, [string]$Target, [string]$Suffix) {
    $temporary = "$Target.$Suffix.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Assert-ProtectedPids([hashtable]$Expected, [int[]]$Ports) {
    foreach ($port in $Ports) {
        $actual = Get-ListenerPid $port
        if (-not $actual -or $actual -ne $Expected[[string]$port]) {
            throw "protected port $port changed: expected=$($Expected[[string]$port]) actual=$actual"
        }
    }
}

function Restart-8094 {
    $listenerPid = Get-ListenerPid 8094
    if (-not $listenerPid) { throw '8094 is not listening before its controlled restart' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid" -ErrorAction Stop
    $listens8093 = Get-NetTCPConnection -LocalPort 8093 -State Listen -OwningProcess $listenerPid -ErrorAction SilentlyContinue
    if (
        $process.Name -ne 'python.exe' -or
        -not $process.CommandLine.Contains('ollama_proxy_server.py') -or
        $process.CommandLine.Contains('ollama_proxy_server_8094.py') -or
        $listens8093
    ) {
        throw '8094 listener is not the expected shared-proxy child'
    }
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if ((Get-ListenerPid 8094) -eq $listenerPid) {
        Stop-Process -Id $listenerPid -Force
    }
    Wait-Port 8094 $false 45
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Wait-Port 8094 $true 120
}

function Wait-HttpMarker([int]$Port, [string]$Path, [string]$Marker, [int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = ''
    do {
        try {
            $uri = "http://127.0.0.1:$Port$Path"
            $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 12
            if ($response.StatusCode -eq 200 -and $response.Content.Contains($Marker)) {
                return [ordered]@{ status = [int]$response.StatusCode; length = [int]$response.RawContentLength }
            }
            $lastError = "status=$($response.StatusCode) marker=$($response.Content.Contains($Marker))"
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "HTTP marker did not become ready on ${Port}${Path}: $lastError"
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "manifest missing: $ManifestPath" }
if (-not (Test-Path -LiteralPath $manager -PathType Leaf)) { throw "8093 manager missing: $manager" }
if (-not (Test-Path -LiteralPath $config8093 -PathType Leaf)) { throw "8093 config missing: $config8093" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python311 missing: $python" }
$proxyBuilder = Join-Path (Split-Path -Parent $ManifestPath) 'build_diag_proxy_payload.py'
$proxyBlockBuilder = Join-Path (Split-Path -Parent $ManifestPath) 'build_8093_diag_single_payload.py'
if (-not (Test-Path -LiteralPath $proxyBuilder -PathType Leaf)) { throw "proxy builder missing: $proxyBuilder" }
if (-not (Test-Path -LiteralPath $proxyBlockBuilder -PathType Leaf)) { throw "proxy block builder missing: $proxyBlockBuilder" }

$manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema -ne 'bf_diag_rules_deploy.v1') { throw 'unsupported deployment manifest schema' }
if ([string]$manifest.projectRoot -ne $root) { throw 'manifest project root does not match the approved V4 root' }
if (@($manifest.targets).Count -ne 2 -or @($manifest.targets) -notcontains 8093 -or @($manifest.targets) -notcontains 8094) {
    throw 'this deployer requires the shared 8093+8094 target pair'
}
$assetVersion = [string]$manifest.assetVersion
if ($assetVersion -notmatch '^diag-[0-9]{8}-[0-9]{4}-[0-9a-f]{10}$') { throw 'invalid asset version' }
$deploymentId = [string]$manifest.deploymentId
if ($deploymentId -notmatch '^diag_rules_[0-9]{8}-[0-9]{4}-[0-9a-f]{10}$') { throw 'invalid deployment id' }

$payloads = @()
foreach ($entry in @($manifest.files)) {
    $relative = [string]$entry.targetRelative
    if ($allowedTargets -notcontains $relative) { throw "target is not allow-listed: $relative" }
    $source = Join-Path ([string]$manifest.stageRoot) ([string]$entry.stagedName)
    $target = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "staged file missing: $source" }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "production target missing: $target" }
    $actualHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    if ($actualHash -ne [string]$entry.sha256) { throw "staged hash mismatch: $relative" }
    $payloads += [pscustomobject]@{ source = $source; target = $target; relative = $relative; sha256 = $actualHash }
}
if ($payloads.Count -ne $allowedTargets.Count) { throw "bundle file count mismatch: $($payloads.Count)" }

$proxyRecord = $payloads | Where-Object { $_.relative -eq '高炉前端数据\智能助手\backend\ollama_proxy_server.py' }
if (-not $proxyRecord) { throw 'staged proxy patch source is missing' }
$proxyPatchSource = $proxyRecord.source
$generatedProxy = Join-Path ([string]$manifest.stageRoot) '00_ollama_proxy_server.generated.py'
& $python $proxyBuilder --base $proxyRecord.target --local $proxyPatchSource --output $generatedProxy --asset-version $assetVersion
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $generatedProxy -PathType Leaf)) {
    throw 'remote-current proxy merge failed'
}
$proxyRecord.source = $generatedProxy
$proxyPayload = $generatedProxy
$proxyText = Get-Content -LiteralPath $proxyPayload -Raw -Encoding UTF8
if (-not $proxyText.Contains($assetVersion) -or -not $proxyText.Contains('/api/diagnosis-core-evidence')) {
    throw 'generated proxy markers are invalid'
}$manualPayload = ($payloads | Where-Object { $_.relative -eq '高炉前端数据\assets\bf-diagnosis-manual-score-local.js' }).source
$manualText = Get-Content -LiteralPath $manualPayload -Raw -Encoding UTF8
if (-not $manualText.Contains('bootWhenBodyReady') -or -not $manualText.Contains('bfdms-core-evidence')) {
    throw 'staged manual-score asset markers are invalid'
}

$pythonSources = @($payloads | Where-Object { $_.source.EndsWith('.py') } | ForEach-Object { $_.source })
& $python -m py_compile @pythonSources
if ($LASTEXITCODE -ne 0) { throw 'staged Python syntax check failed' }

$before = @{}
foreach ($port in @(8093, 8094, 8768, 8770, 11434)) {
    $listenerPid = Get-ListenerPid $port
    if (-not $listenerPid) { throw "required port $port is not listening" }
    $before[[string]$port] = $listenerPid
}
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State.ToString() -eq 'Disabled') { throw '8094 preview task is disabled' }

$backupRoot = Join-Path $root "logs\deploy_backups\$deploymentId"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backups = @()
foreach ($payload in $payloads) {
    $backup = Join-Path $backupRoot ([IO.Path]::GetFileName($payload.target))
    if (Test-Path -LiteralPath $backup) { $backup = Join-Path $backupRoot (([Guid]::NewGuid().ToString('N')) + '_' + [IO.Path]::GetFileName($payload.target)) }
    Copy-Item -LiteralPath $payload.target -Destination $backup -Force
    $backups += [pscustomobject]@{ backup = $backup; target = $payload.target }
}

try {
    $lockTaken = $deploymentMutex.WaitOne([TimeSpan]::FromSeconds(45))
    if (-not $lockTaken) { throw 'timed out waiting for the diagnosis deployment mutex' }

    Invoke-8093Manager 'stop'
    $guardPaused = $true
    Wait-Port 8093 $false 30
    Assert-ProtectedPids $before @(8094, 8768, 8770, 11434)

    foreach ($payload in $payloads) {
        Install-Atomically $payload.source $payload.target $deploymentId
    }
    $filesApplied = $true

    Invoke-8093Manager 'start'
    Wait-Port 8093 $true 120
    $guardRestored = $true
    $pid8093After = Get-ListenerPid 8093
    Assert-ProtectedPids $before @(8094, 8768, 8770, 11434)

    Restart-8094
    Assert-ProtectedPids $before @(8768, 8770, 11434)
    if ((Get-ListenerPid 8093) -ne $pid8093After) { throw '8093 changed while restarting 8094' }

    $page8093 = Wait-HttpMarker 8093 "/?deploy=$deploymentId" $assetVersion 60
    $page8094 = Wait-HttpMarker 8094 "/?deploy=$deploymentId" $assetVersion 60
    $asset8093 = Wait-HttpMarker 8093 "/assets/bf-diagnosis-manual-score-local.js?deploy=$deploymentId" 'bootWhenBodyReady' 45
    $asset8094 = Wait-HttpMarker 8094 "/assets/bf-diagnosis-manual-score-local.js?deploy=$deploymentId" 'bootWhenBodyReady' 45

    [ordered]@{
        ok = $true
        schema = 'bf_diag_rules_deploy_receipt.v1'
        operation = 'OPS-DIAG-RULES-ONE-CLICK-DEPLOY'
        deploymentId = $deploymentId
        assetVersion = $assetVersion
        backup = $backupRoot
        guardPaused = $guardPaused
        guardRestored = $guardRestored
        rollbackApplied = $rollbackApplied
        pidBefore = $before
        pidAfter = [ordered]@{
            '8093' = Get-ListenerPid 8093
            '8094' = Get-ListenerPid 8094
            '8768' = Get-ListenerPid 8768
            '8770' = Get-ListenerPid 8770
            '11434' = Get-ListenerPid 11434
        }
        http = [ordered]@{ '8093' = $page8093; '8094' = $page8094 }
        assets = [ordered]@{ '8093' = $asset8093; '8094' = $asset8094 }
        protectedPidsUnchanged = $true
        elapsedSeconds = [Math]::Round(((Get-Date) - $startedAt).TotalSeconds, 2)
        files = @($payloads | ForEach-Object { [ordered]@{ target = $_.target; sha256 = (Get-FileHash -LiteralPath $_.target -Algorithm SHA256).Hash } })
    } | ConvertTo-Json -Depth 8
}
catch {
    $primaryError = $_.Exception.Message
    if ($filesApplied) {
        try {
            if (Get-ListenerPid 8093) {
                Invoke-8093Manager 'stop'
                Wait-Port 8093 $false 30
            }
            foreach ($entry in $backups) {
                Install-Atomically $entry.backup $entry.target "rollback-$deploymentId"
            }
            Invoke-8093Manager 'start'
            Wait-Port 8093 $true 120
            $guardRestored = $true
            Restart-8094
            Assert-ProtectedPids $before @(8768, 8770, 11434)
            $rollbackApplied = $true
        }
        catch {
            throw "deployment failed: $primaryError; rollback also failed: $($_.Exception.Message)"
        }
    }
    throw "deployment failed: $primaryError; rollbackApplied=$rollbackApplied"
}
finally {
    if ($guardPaused -and -not (Get-ListenerPid 8093)) {
        try {
            Invoke-8093Manager 'start'
            Wait-Port 8093 $true 120
            $guardRestored = $true
        }
        catch {
            Write-Error "8093 final recovery failed: $($_.Exception.Message)"
        }
    }
    if ($lockTaken) { $deploymentMutex.ReleaseMutex() }
    $deploymentMutex.Dispose()
}
