[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedArtifactSha256,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedBaselineSha256,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedPlanSha256,
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedGitHead,
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_qa_copy_recommendations_20260814'
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

$RequirementId = 'REQ-QA-LOCAL-RECOMMENDATION-PRESERVATION-20260814'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Relative = '高炉前端数据\frontend_dashboard_v3.server.html'
$Target = Join-Path $Root $Relative
$Stage = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
$PlanPath = Join-Path $StageRoot 'delta-plan.json'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
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

foreach ($Required in @($Stage, $PlanPath, $Target, $Manager, $ConfigPath, $Pwsh, $GitExe)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing required input: $Required" }
}
$ExpectedArtifactSha256 = $ExpectedArtifactSha256.ToUpperInvariant()
$ExpectedBaselineSha256 = $ExpectedBaselineSha256.ToUpperInvariant()
$ExpectedPlanSha256 = $ExpectedPlanSha256.ToUpperInvariant()
$Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
if ($Head -ne $ExpectedGitHead) { throw "Production Git HEAD drifted: $Head" }
if ((Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash -ne $ExpectedArtifactSha256) {
    throw 'Staged artifact SHA-256 mismatch.'
}
if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $ExpectedBaselineSha256) {
    throw 'Production baseline SHA-256 drifted.'
}
if ((Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash -ne $ExpectedPlanSha256) {
    throw 'Delta plan SHA-256 mismatch.'
}
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne $RequirementId) {
    throw 'Delta plan identity mismatch.'
}
$Changes = @($Plan.changes)
if ($Changes.Count -ne 1) { throw 'Deployment requires exactly one delta target.' }
$PlannedTarget = [IO.Path]::GetFullPath([string]$Changes[0].target)
if (-not [string]::Equals($PlannedTarget, [IO.Path]::GetFullPath($Target), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Delta plan target is outside the exact HTML allowlist.'
}
if (([string]$Changes[0].desired_sha256).ToUpperInvariant() -ne $ExpectedArtifactSha256) {
    throw 'Delta plan desired SHA-256 mismatch.'
}
$PlanBaselines = @($Changes[0].baseline_sha256 | ForEach-Object { ([string]$_).ToUpperInvariant() })
if ($PlanBaselines.Count -ne 1 -or $PlanBaselines[0] -ne $ExpectedBaselineSha256) {
    throw 'Delta plan baseline allowlist mismatch.'
}
$StageText = Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
$RequiredMarkers = @(
    'REQ-QA-MESSAGE-COPY-20260814',
    'qa-message-copy',
    '复制问题',
    '复制回复',
    '原有常用问题',
    '常用 MCP 模板',
    'aria-label="可滚动推荐问题列表"',
    '__BF_QA_EXEC_TRACE__',
    'function QaGuestNav',
    '登录私有会话（可选）',
    "accessMode === 'guest_shared'"
)
foreach ($Marker in $RequiredMarkers) {
    if (-not $StageText.Contains($Marker)) { throw "Artifact marker missing: $Marker" }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
$Stopped = $false
$Installed = $false
$Rollback = $false
$OldPid = $null
$NewPid = $null
$ProtectedBefore = $null
$BackupRoot = Join-Path $Root ('backups\qa_copy_recommendations_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
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
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $ExpectedArtifactSha256) {
        throw 'Installed SHA-256 mismatch.'
    }

    Invoke-ServiceAction 'start'
    $Stopped = $false
    Wait-Port 8093 $true 180
    $NewPid = Get-ListenerPid 8093
    if (-not $NewPid -or $NewPid -eq $OldPid) { throw '8093 did not start with a new PID.' }
    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/高炉前端数据/frontend_dashboard_v3.server.html?deploy=$ExecutionId#qa" -TimeoutSec 45
    if ($Page.StatusCode -ne 200) { throw "Production dashboard returned HTTP $($Page.StatusCode)." }
    foreach ($Marker in $RequiredMarkers) {
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
        backup = $BackupRoot
        old_8093_pid = $OldPid
        new_8093_pid = $NewPid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        http_8093 = [int]$Page.StatusCode
        bootstrap_access_mode = [string]$Bootstrap.access_mode
        installed_sha256 = $ExpectedArtifactSha256
        rollback_applied = $false
        rollback_scope = 'application_file_only'
        guard_restored = $true
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
        rollback_scope = 'application_file_only'
        guard_restored = ((Get-Service -Name $ServiceName).Status -eq 'Running')
        listener_8093 = Get-ListenerPid 8093
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw $Failure
} finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
