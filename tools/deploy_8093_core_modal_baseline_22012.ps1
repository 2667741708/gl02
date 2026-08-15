[CmdletBinding()]
param([string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-CORE-PORTAL-BASELINE-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$RemoteSession = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_8093_core_modal_baseline.ps1'
$ManifestTool = 'C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$Manifest = Join-Path $Root '.tmp\core-modal-baseline-20260811\prepared-release.json'
$DeltaPlan = Join-Path $Root '.tmp\core-modal-baseline-20260811\delta-plan.json'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\8093_core_portal_baseline_20260811'
$Html = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.production.html'
$Bundle = Join-Path $Root '高炉前端数据\assets\build\dashboard-main-CcxwpZA4.js'

foreach ($Path in @($RemoteSession, $RemoteDeploy, $ManifestTool, $Manifest, $DeltaPlan, $Html, $Bundle)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required local file missing: $Path" }
}

$Total = [Diagnostics.Stopwatch]::StartNew()
$PhaseTimings = [ordered]@{}

function Invoke-Timed {
    param([string]$Name, [scriptblock]$Action)
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    try { return & $Action }
    finally {
        $Timer.Stop()
        $script:PhaseTimings[$Name] = $Timer.ElapsedMilliseconds
    }
}

$VerifyRaw = Invoke-Timed -Name 'manifest_verify' -Action {
    (& $Python $ManifestTool verify --manifest $Manifest | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Prepared release manifest verification failed.' }
$Verify = $VerifyRaw | ConvertFrom-Json
if (-not $Verify.ok) { throw 'Prepared release manifest is not valid.' }

$Plan = Get-Content -LiteralPath $DeltaPlan -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne $RequirementId) {
    throw 'Delta plan identity mismatch.'
}
if (@($Plan.changes).Count -ne 2) { throw 'Expected exactly two changed artifacts.' }

$EnsureRaw = Invoke-Timed -Name 'session_ensure' -Action {
    (& $Python $RemoteSession ensure --allow-agents-password --workdir $RemoteRoot | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH session ensure failed.' }
$Ensure = $EnsureRaw | ConvertFrom-Json
if (-not $Ensure.ok -or -not $Ensure.ssh_active) { throw 'Persistent SSH session is not active.' }

$UploadArgs = @(
    $RemoteSession, 'run', '--', '--no-profile', '--timeout', '90', '--workdir', $RemoteRoot,
    '--upload-only',
    '--upload', "$Html=$RemoteStage\frontend_dashboard_v3.server.html",
    '--upload', "$Bundle=$RemoteStage\dashboard-main-CcxwpZA4.js"
)
$UploadRaw = Invoke-Timed -Name 'upload_only' -Action {
    (& $Python @UploadArgs | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed; production was not changed.' }
$Upload = $UploadRaw | ConvertFrom-Json
if (-not $Upload.ok -or $Upload.uncertain_execution) { throw 'Upload-only result was not trustworthy.' }
if ($Upload.session_id -ne $Ensure.session_id -or $Upload.connection_id -ne $Ensure.connection_id) {
    throw 'SSH connection identity changed during staging.'
}

$DeployRaw = Invoke-Timed -Name 'guarded_deploy' -Action {
    (& $Python $RemoteSession run -- --no-profile --timeout 180 --workdir $RemoteRoot --script $RemoteDeploy | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Guarded deployment failed; inspect remote rollback evidence.' }
$Deploy = $DeployRaw | ConvertFrom-Json
if (-not $Deploy.ok -or $Deploy.uncertain_execution) { throw 'Guarded deployment result was not trustworthy.' }
if ($Deploy.session_id -ne $Ensure.session_id -or $Deploy.connection_id -ne $Ensure.connection_id) {
    throw 'SSH connection identity changed during deployment.'
}
if ([int]$Deploy.request_count -le [int]$Upload.request_count) { throw 'SSH request counter did not increase.' }

$JsonStart = $Deploy.stdout.IndexOf('{')
$JsonEnd = $Deploy.stdout.LastIndexOf("`n[exit]")
if ($JsonStart -lt 0 -or $JsonEnd -le $JsonStart) { throw 'Remote acceptance JSON was not found.' }
$RemoteResult = $Deploy.stdout.Substring($JsonStart, $JsonEnd - $JsonStart).Trim() | ConvertFrom-Json
if (
    -not $RemoteResult.ok -or
    -not $RemoteResult.mutex_acquired -or
    -not $RemoteResult.guard_paused -or
    -not $RemoteResult.guard_restored -or
    $RemoteResult.rollback_applied
) {
    throw 'Remote acceptance fields did not prove successful guarded deployment.'
}

$StatusRaw = Invoke-Timed -Name 'session_postcheck' -Action {
    (& $Python $RemoteSession status | Out-String).Trim()
}
if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH postcheck failed.' }
$Status = $StatusRaw | ConvertFrom-Json
if (-not $Status.ok -or -not $Status.ssh_active) { throw 'Persistent SSH session is not healthy after deployment.' }
if ($Status.session_id -ne $Ensure.session_id -or $Status.connection_id -ne $Ensure.connection_id) {
    throw 'Persistent SSH connection identity changed after deployment.'
}

$Total.Stop()
[pscustomobject]@{
    ok = $true
    requirement_id = $RequirementId
    manifest_sha256 = $Plan.manifest_sha256
    session_id = $Ensure.session_id
    connection_id = $Ensure.connection_id
    request_count_before = $Ensure.request_count
    request_count_after = $Status.request_count
    total_duration_ms = $Total.ElapsedMilliseconds
    phase_duration_ms = $PhaseTimings
    upload_transport = $Upload
    deploy_transport = $Deploy
    remote_result = $RemoteResult
} | ConvertTo-Json -Depth 12
