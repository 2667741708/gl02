[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core or later is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-8093-ABC33-B4-CANONICAL-SCORE-20260810'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_b4_score_source_20260810_v2'
$ServiceName = 'BFV4PreviewProxy8093'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\abc33_b4_score_source_8093_$Stamp"
$Files = @(
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'diagnosis_review.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_review.py'; Baseline = '541822B4CE30A14EB1B9CA9DC0B05EE0E87023DAF1E86804EF511954B756486A'; Markers = @('apply_abc33_display_score', 'diagnosis-review-score-source.v2') },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'diagnosis_model_review.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_model_review.py'; Baseline = '905614B5FDF62A7F1453CD1EDE36770D851DC7D2B6433AFA9E884B6172F19908'; Markers = @('v7-abc33-b4', 'score_sources') },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'ollama_proxy_server.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'; Baseline = 'ED84AD575D2B3D6DB87FA57F5CADC36EB2C792BE43E3534B155200A0A46E4D41'; Markers = @('load_latest_abc33_review_score', '20260810-abc33-b4-score-r1') },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf-diagnosis-review-local.js'; Target = Join-Path $Root '高炉前端数据\assets\bf-diagnosis-review-local.js'; Baseline = 'D8906D914908A4393FD960348F46E1C3A3FA1CF46EE778EAD5A72321B5C4B863'; Markers = @('display_main_score', '统一采用ABC33') },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf-diagnosis-manual-score-local.js'; Target = Join-Path $Root '高炉前端数据\assets\bf-diagnosis-manual-score-local.js'; Baseline = '02563549A89ACBA7FFF4F3217AE69EAF02F068C14648C44C9BEBDEE237C71A0C'; Markers = @('ctx.display_scores||ctx.raw_scores', 'scoreText=Number.isFinite(systemScore)?systemScore.toFixed(1):"--"') }
)

function Get-ListenerPidMap {
    param([int[]]$Ports)
    $Wanted = @{}; foreach ($Port in $Ports) { $Wanted[$Port] = $true }
    $Found = @{}
    Get-NetTCPConnection -State Listen -ErrorAction Stop | ForEach-Object {
        if ($Wanted.ContainsKey([int]$_.LocalPort) -and -not $Found.ContainsKey([int]$_.LocalPort)) { $Found[[int]$_.LocalPort] = [int]$_.OwningProcess }
    }
    $Result = [ordered]@{}; foreach ($Port in $Ports) { $Result[[string]$Port] = $Found[[int]$Port] }
    return $Result
}
function Get-ListenerPid { param([int]$Port) return (Get-ListenerPidMap -Ports @($Port))[[string]$Port] }
function Wait-ServiceState {
    param([string]$Desired, [int]$TimeoutSeconds = 60)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$ServiceName did not reach $Desired."
}
function Wait-PortState {
    param([bool]$Listening, [int]$TimeoutSeconds = 60)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port 8093) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port 8093 did not reach listening=$Listening."
}
function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 stop failed.' }
    Wait-ServiceState -Desired 'Stopped'
    Wait-PortState -Listening $false
}
function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 start failed.' }
    Wait-ServiceState -Desired 'Running'
    Wait-PortState -Listening $true
}
function Assert-BelowRoot {
    param([string]$Path)
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $ResolvedPath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Target escapes production root: $Path" }
}
function Install-Atomically {
    param([string]$Source, [string]$Target)
    Assert-BelowRoot -Path $Target
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($Pwsh, $Python, $Manager, $ConfigPath) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing deployment input: $Required" }
}
foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    if (-not (Test-Path -LiteralPath $File.Target -PathType Leaf)) { throw "Production target missing: $($File.Target)" }
    $CurrentHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
    if ($CurrentHash -ne $File.Baseline) { throw "Unreviewed baseline: $($File.Target) $CurrentHash" }
    $Text = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
    foreach ($Marker in $File.Markers) { if (-not $Text.Contains($Marker)) { throw "Staged marker missing: $Marker" } }
}
$StagedPython = @($Files | Where-Object { $_.Stage.EndsWith('.py') } | ForEach-Object { $_.Stage })
& $Python -m py_compile @StagedPython
if ($LASTEXITCODE -ne 0) { throw 'Staged Python syntax validation failed.' }

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAcquired = $false
$GuardPaused = $false
$GuardRestored = $false
$RollbackApplied = $false
$Old8093Pid = $null
$New8093Pid = $null
$ProtectedBefore = $null
$ProtectedAfter = $null
$Previous = @{}
$InstalledHashes = [ordered]@{}
try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment or recovery owns the deployment mutex.' }
    $ProtectedBefore = Get-ListenerPidMap -Ports $ProtectedPorts
    foreach ($Key in $ProtectedBefore.Keys) { if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening." } }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 service is not running.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw '8093 is not listening.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = $File.Target.Substring($Root.Length).TrimStart('\')
        $Backup = Join-Path $BackupRoot $Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
        Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        $Previous[$File.Target] = $Backup
    }

    Stop-8093
    $GuardPaused = $true
    $ProtectedPaused = Get-ListenerPidMap -Ports $ProtectedPorts
    foreach ($Key in $ProtectedBefore.Keys) { if ($ProtectedPaused[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed while paused: $Key" } }
    foreach ($File in $Files) {
        Install-Atomically -Source $File.Stage -Target $File.Target
        $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
        $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($StageHash -ne $TargetHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $TargetHash
    }
    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not start with a new listener PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=abc33-b4-source-$Stamp" -TimeoutSec 45
    $ReviewAsset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf-diagnosis-review-local.js?cb=$Stamp" -TimeoutSec 45
    $ManualAsset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf-diagnosis-manual-score-local.js?cb=$Stamp" -TimeoutSec 45
    if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains('20260810-abc33-b4-score-r1')) { throw '8093 page marker verification failed.' }
    if (-not $ReviewAsset.Content.Contains('统一采用ABC33')) { throw 'Review asset marker verification failed.' }
    if (-not $ManualAsset.Content.Contains('ctx.display_scores||ctx.raw_scores')) { throw 'Manual score asset marker verification failed.' }
    $Latest = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/furnace-rules/latest?cb=$Stamp" -TimeoutSec 45
    $Detail = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/furnace-rules/B4/detail?cb=$Stamp" -TimeoutSec 45
    $ContextResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/diagnosis-review-context?cb=$Stamp" -TimeoutSec 45
    $Context = $ContextResponse.context
    if (-not $ContextResponse.ok -or -not $Context.available) { throw 'Diagnosis review context is unavailable.' }
    if ($Context.score_contract_version -ne 'diagnosis-review-score-source.v2') { throw 'Score source contract marker is missing.' }
    if ($Context.score_sources.hot.rule_id -ne 'B4' -or $Context.score_sources.hot.fallback_used) { throw 'Hot score is not exclusively sourced from ABC33 B4.' }
    if ($null -eq $Context.legacy_score_archive.hot.score) { throw 'Legacy hot score archive metadata is missing.' }
    if ($Context.score_sources.hot.state -eq 'current' -and $null -eq $Context.display_scores.hot) { throw 'Current B4 source has no display score.' }
    if ($Context.score_sources.hot.state -ne 'current' -and $null -ne $Context.display_scores.hot) { throw 'Unavailable B4 source did not fail closed.' }
    if ($Latest.evaluation_id -eq $Detail.evaluation_id -and $Latest.batch_state -ne $Detail.batch_state) { throw 'Latest and detail freshness states differ.' }
    $B4 = @($Latest.rules | Where-Object { $_.rule_id -eq 'B4' }) | Select-Object -First 1
    if ($Context.score_sources.hot.evaluation_id -eq $Latest.evaluation_id -and $Context.display_scores.hot -ne $B4.score) { throw 'Popup and ABC B4 differ for the same evaluation.' }
    $ProtectedAfter = Get-ListenerPidMap -Ports $ProtectedPorts
    foreach ($Key in $ProtectedBefore.Keys) { if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" } }

    [pscustomobject]@{
        ok = $true; requirement_id = $RequirementId; backup = $BackupRoot
        guard_paused = $GuardPaused; guard_restored = $GuardRestored; rollback_applied = $false
        old_8093_pid = $Old8093Pid; new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore; protected_after = $ProtectedAfter
        installed_hashes = $InstalledHashes; http_8093 = [int]$Page.StatusCode
        latest_evaluation_id = $Latest.evaluation_id; latest_b4_score = $B4.score
        context_evaluation_id = $Context.score_sources.hot.evaluation_id
        context_display_hot = $Context.display_scores.hot; context_legacy_hot = $Context.legacy_score_archive.hot.score
        context_source_state = $Context.score_sources.hot.state
    } | ConvertTo-Json -Depth 8
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
        foreach ($Target in $Previous.Keys) { Copy-Item -LiteralPath $Previous[$Target] -Destination $Target -Force }
        if ($Previous.Count -gt 0) { $RollbackApplied = $true }
    }
    finally {
        if ($Old8093Pid) { Start-8093; $GuardRestored = $true }
    }
    [pscustomobject]@{ ok = $false; requirement_id = $RequirementId; failure = $Failure; backup = $BackupRoot; guard_paused = $GuardPaused; guard_restored = $GuardRestored; rollback_applied = $RollbackApplied; listener_8093 = Get-ListenerPid -Port 8093 } | ConvertTo-Json -Depth 5 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
