[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedPlanSha256,
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedGitHead,
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_guest_ui_recovery_20260814'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-GUEST-UI-RECOVERY-20260814'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$PlanPath = Join-Path $StageRoot 'delta-plan.json'
$Stage = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
$Relative = '高炉前端数据\frontend_dashboard_v3.server.html'
$Target = Join-Path $Root $Relative
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434, 8892)

function Get-ListenerPid([int]$Port) {
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Result = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Result[[string]$Port] = Get-ListenerPid $Port }
    return $Result
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 120) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening."
}

function Invoke-ServiceAction([string]$Action) {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action $Action -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Service action $Action failed with exit code $LASTEXITCODE." }
}

foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $GitExe, $PlanPath, $Stage, $Target)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing required input: $Required" }
}
$Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
if ($Head -ne $ExpectedGitHead) { throw "Production Git HEAD drifted: $Head" }
$ActualPlanSha256 = (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash
if ($ActualPlanSha256 -ne $ExpectedPlanSha256.ToUpperInvariant()) { throw 'Delta plan SHA-256 mismatch.' }
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne $RequirementId) {
    throw 'Delta plan identity mismatch.'
}
$Changes = @($Plan.changes)
if ($Changes.Count -ne 1) {
    throw 'This deployment accepts exactly one reviewed dashboard target.'
}
$PlannedTarget = [IO.Path]::GetFullPath([string]$Changes[0].target)
$ExpectedTarget = [IO.Path]::GetFullPath($Target)
if (-not [string]::Equals($PlannedTarget, $ExpectedTarget, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'This deployment accepts exactly the reviewed dashboard target.'
}
$Change = $Changes[0]
$Desired = ([string]$Change.desired_sha256).ToUpperInvariant()
$Baselines = @($Change.baseline_sha256 | ForEach-Object { ([string]$_).ToUpperInvariant() })
if ((Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash -ne $Desired) { throw 'Staged artifact hash mismatch.' }
$Current = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
if ($Baselines -notcontains $Current) { throw "Production baseline drift: $Current" }
$StageText = Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
foreach ($Marker in @($Change.markers)) {
    if (-not $StageText.Contains([string]$Marker)) { throw "Artifact marker missing: $Marker" }
}
foreach ($Marker in @('function QaGuestNav', '登录私有会话（可选）', '继续匿名使用', "accessMode === 'guest_shared'")) {
    if (-not $StageText.Contains($Marker)) { throw "Guest UI marker missing: $Marker" }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
$Stopped = $false
$Installed = $false
$Rollback = $false
$OldPid = $null
$NewPid = $null
$ProtectedBefore = $null
$BackupRoot = Join-Path $Root ('backups\guest_ui_recovery_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$Backup = Join-Path $BackupRoot $Relative
try {
    try { $Acquired = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $Acquired = $true }
    if (-not $Acquired) { throw 'Another 8093 deployment owns the mutex.' }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 service is not running.' }
    $OldPid = Get-ListenerPid 8093
    if (-not $OldPid) { throw '8093 is not listening.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening." }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
    Copy-Item -LiteralPath $Target -Destination $Backup -Force

    Invoke-ServiceAction 'stop'
    $Stopped = $true
    Wait-Port 8093 $false
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid ([int]$Key)) -ne $ProtectedBefore[$Key]) { throw "Protected port $Key changed during stop." }
    }
    $Temporary = "$Target.deploying-$ExecutionId"
    Copy-Item -LiteralPath $Stage -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
    $Installed = $true
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $Desired) { throw 'Installed hash mismatch.' }

    Invoke-ServiceAction 'start'
    $Stopped = $false
    Wait-Port 8093 $true 180
    $NewPid = Get-ListenerPid 8093
    if (-not $NewPid -or $NewPid -eq $OldPid) { throw '8093 did not start with a new PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/高炉前端数据/frontend_dashboard_v3.server.html?deploy=$ExecutionId#qa" -TimeoutSec 45
    if ($Page.StatusCode -ne 200) { throw "Production dashboard returned HTTP $($Page.StatusCode)." }
    foreach ($Marker in @('function QaGuestNav', '登录私有会话（可选）', '继续匿名使用')) {
        if (-not $Page.Content.Contains($Marker)) { throw "Served page marker missing: $Marker" }
    }
    $Bootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 30
    if (-not $Bootstrap.ok -or $Bootstrap.access_mode -ne 'guest_shared' -or -not $Bootstrap.conversation.id) {
        throw 'Anonymous bootstrap did not return the shared guest conversation.'
    }
    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        plan_sha256 = $ActualPlanSha256
        backup = $BackupRoot
        old_8093_pid = $OldPid
        new_8093_pid = $NewPid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        http_8093 = [int]$Page.StatusCode
        bootstrap_access_mode = [string]$Bootstrap.access_mode
        installed_sha256 = $Desired
        guard_paused = $true
        guard_restored = $true
        rollback_applied = $false
    } | ConvertTo-Json -Depth 7
} catch {
    $Failure = $_.Exception.Message
    try {
        if ($Installed) {
            if (-not $Stopped) {
                Invoke-ServiceAction 'stop'
                Wait-Port 8093 $false
                $Stopped = $true
            }
            Copy-Item -LiteralPath $Backup -Destination $Target -Force
            $Rollback = $true
        }
    } finally {
        if ($Stopped) {
            Invoke-ServiceAction 'start'
            Wait-Port 8093 $true 180
            $Stopped = $false
        }
    }
    [ordered]@{
        ok = $false
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        failure = $Failure
        backup = $BackupRoot
        rollback_applied = $Rollback
        guard_restored = ((Get-Service -Name $ServiceName).Status -eq 'Running')
        listener_8093 = Get-ListenerPid 8093
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw $Failure
} finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
