[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\diagnosis_ai_json_fix_20260811'
$DeltaPlanPath = Join-Path $StageRoot 'delta-plan.json'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$Target = Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_review.py'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\diagnosis_ai_json_fix_8093_$Stamp"

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) {
        $Map[[string]$Port] = Get-ListenerPid -Port $Port
    }
    return $Map
}

function Wait-ServiceState {
    param([string]$Desired, [int]$TimeoutSeconds = 60)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $Status = (Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString()
        if ($Status -eq $Desired) { return }
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
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath |
        Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 stop failed.' }
    Wait-ServiceState -Desired 'Stopped'
    Wait-PortState -Listening $false
}

function Start-8093 {
    Start-Sleep -Seconds 15
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath |
        Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 start failed.' }
    Wait-ServiceState -Desired 'Running'
    Wait-PortState -Listening $true
}

function Install-Atomically {
    param([string]$Source, [string]$Destination)
    if ([IO.Path]::GetFullPath($Destination) -ne [IO.Path]::GetFullPath($Target)) {
        throw "Target is not allowlisted: $Destination"
    }
    $Temporary = "$Destination.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Destination -Force
}

function Wait-DiagnosisAnalysis {
    param([string]$Label = 'normal', [int]$TimeoutSeconds = 240)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $Uri = "http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=$Label&deploy=$Stamp"
    do {
        $Response = Invoke-RestMethod -Uri $Uri -TimeoutSec 45
        $State = [string]$Response.analysis.state
        if ($State -eq 'completed') { return $Response.analysis }
        if ($State -eq 'failed') {
            throw "Diagnosis AI analysis failed after deployment: $($Response.analysis.last_error_code)"
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $Deadline)
    throw 'Diagnosis AI analysis did not complete within the acceptance timeout.'
}

foreach ($Required in @($DeltaPlanPath, $Manager, $ConfigPath, $Pwsh, $Python, $Target)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Missing deployment input: $Required"
    }
}
$DeltaPlan = Get-Content -LiteralPath $DeltaPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($DeltaPlan.schema -ne 'bf.deploy.delta-plan.v1' -or
    $DeltaPlan.requirement_id -ne $RequirementId) {
    throw 'Delta plan schema or requirement mismatch.'
}
$Changes = @($DeltaPlan.changes)
if ($Changes.Count -ne 1) { throw "Expected exactly one deployment change, got $($Changes.Count)." }
$Change = $Changes[0]
if ([IO.Path]::GetFullPath([string]$Change.target) -ne [IO.Path]::GetFullPath($Target)) {
    throw 'Delta plan target is not the diagnosis review backend.'
}
$Stage = [string]$Change.stage
if (-not (Test-Path -LiteralPath $Stage -PathType Leaf)) { throw "Staged file missing: $Stage" }
$StageHash = (Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash
$CurrentHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
if ($StageHash -ne [string]$Change.desired_sha256) { throw 'Staged SHA-256 mismatch.' }
if (@($Change.baseline_sha256) -notcontains $CurrentHash) { throw "Unreviewed baseline: $CurrentHash" }
$StageText = Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
foreach ($Marker in @($Change.markers)) {
    if (-not $StageText.Contains([string]$Marker)) { throw "Staged marker missing: $Marker" }
}
& $Python -m py_compile $Stage
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
$Backup = Join-Path $BackupRoot '高炉前端数据\智能助手\backend\diagnosis_review.py'

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment owns the global mutex.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening." }
    }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') {
        throw '8093 service is not running before deployment.'
    }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw '8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
    Copy-Item -LiteralPath $Target -Destination $Backup -Force

    Stop-8093
    $GuardPaused = $true
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid -Port ([int]$Key)) -ne $ProtectedBefore[$Key]) {
            throw "Protected PID changed while 8093 was paused: $Key"
        }
    }
    Install-Atomically -Source $Stage -Destination $Target
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $StageHash) {
        throw 'Installed SHA-256 mismatch.'
    }
    & $Python -m py_compile $Target
    if ($LASTEXITCODE -ne 0) { throw 'Installed Python syntax validation failed.' }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) {
        throw '8093 did not restart with a new listener PID.'
    }
    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -TimeoutSec 45
    if ($Page.StatusCode -ne 200) { throw '8093 main page did not return HTTP 200.' }
    $ContextResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/diagnosis-review-context?deploy=$Stamp" -TimeoutSec 45
    if (-not $ContextResponse.ok -or -not $ContextResponse.context.available) {
        throw 'Diagnosis review context is unavailable after deployment.'
    }
    $EvaluationTimestamp = [string]$ContextResponse.context.score_sources.hot.evaluation_ts
    if ([string]::IsNullOrWhiteSpace($EvaluationTimestamp)) {
        throw 'ABC33 evaluation timestamp is missing after deployment.'
    }
    $Analysis = Wait-DiagnosisAnalysis -Label 'normal'
    if (-not $Analysis.analysis -or [string]::IsNullOrWhiteSpace([string]$Analysis.analysis.summary)) {
        throw 'Diagnosis AI analysis completed without a usable answer.'
    }
    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [ordered]@{
        schema = 'ops.8093.diagnosis-ai-json-fix.acceptance.v1'
        ok = $true
        notify_immediately = $true
        requirement_id = $RequirementId
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        installed_sha256 = $StageHash
        http_8093 = [int]$Page.StatusCode
        evaluation_ts = $EvaluationTimestamp
        diagnosis_analysis = [ordered]@{
            state = [string]$Analysis.state
            target_label = [string]$Analysis.target_label
            attempt_count = [int]$Analysis.attempt_count
            summary_chars = ([string]$Analysis.analysis.summary).Length
        }
    } | ConvertTo-Json -Depth 9
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') {
            Stop-8093
        }
        if (Test-Path -LiteralPath $Backup -PathType Leaf) {
            Copy-Item -LiteralPath $Backup -Destination $Target -Force
            $RollbackApplied = $true
        }
    }
    finally {
        if ($Old8093Pid) {
            Start-8093
            $GuardRestored = $true
        }
    }
    [ordered]@{
        schema = 'ops.8093.diagnosis-ai-json-fix.acceptance.v1'
        ok = $false
        requirement_id = $RequirementId
        failure = $Failure
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
