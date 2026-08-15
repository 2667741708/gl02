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

$RequirementId = 'REQ-8093-FRONTEND-PERF-R1'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$RemoteSession = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_8093_frontend_perf.ps1'
$BuildScript = Join-Path $Root '高炉前端数据\dashboard_build\scripts\build-dashboard.mjs'
$BaselineHtml = Join-Path $Root '.tmp\8093-frontend-perf-baseline\frontend_dashboard_v3.server.html'
$StageRoot = Join-Path $Root '.tmp\8093-frontend-perf-stage'
$StageBuild = Join-Path $StageRoot 'assets\build'
$StageHtml = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
$VerifyOutput = Join-Path $Root '.tmp\8093-frontend-perf-deploy-verification'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\8093_frontend_perf_r1_20260810'
$MemoryScript = 'C:\Users\hmw20\.codex\skills\deploy-8093-guarded-update\scripts\deployment_memory.py'
$PythonLibs = Join-Path $Root '.tmp_pylibs'
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$Node = (Get-Command -Name node -ErrorAction Stop).Source
$Expected = [ordered]@{
    'frontend_dashboard_v3.server.html' = '742945363CC45D662559824D1C319B91ADA32A6FED9B273A3FE2E049D9120C38'
    'dashboard-main-v9ebK4cf.js' = '0DAD8EEB8B453F5093D8EAAFA8369B87E3C33DA01DBE2CE4186C4563BFD04475'
    'overview-route-loader-Bv2DvOlP.js' = '3DE19416A94C1CC96E07AD810EB1AA6853838600F40B6A9FBC86294C14DDA399'
}
$Uploads = @(
    "$StageHtml=$RemoteStage\frontend_dashboard_v3.server.html",
    "$(Join-Path $StageBuild 'dashboard-main-v9ebK4cf.js')=$RemoteStage\dashboard-main-v9ebK4cf.js",
    "$(Join-Path $StageBuild 'overview-route-loader-Bv2DvOlP.js')=$RemoteStage\overview-route-loader-Bv2DvOlP.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf-shared-runtime-scheduler.js')=$RemoteStage\bf-shared-runtime-scheduler.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf-core-metrics-pspace-live-8093.js')=$RemoteStage\bf-core-metrics-pspace-live-8093.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js')=$RemoteStage\bf3d-furnace-body-billboard-adapter.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf3d-physical-point-filter-8093.js')=$RemoteStage\bf3d-physical-point-filter-8093.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf3d-surface-camera-guard-8093.js')=$RemoteStage\bf3d-surface-camera-guard-8093.js",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py')=$RemoteStage\ollama_proxy_server.py",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\http_static_compression.py')=$RemoteStage\http_static_compression.py"
)

foreach ($Path in @($RemoteSession, $RemoteDeploy, $BuildScript, $BaselineHtml, $MemoryScript)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required local file missing: $Path" }
}

$TotalTimer = [Diagnostics.Stopwatch]::StartNew()
$Phase = 'local_validation'
$PhaseTimings = [ordered]@{}
$PreviousPythonPath = $env:PYTHONPATH
if (Test-Path -LiteralPath $PythonLibs -PathType Container) { $env:PYTHONPATH = $PythonLibs }

function Start-Phase {
    param([string]$Name)
    $script:Phase = $Name
    return [Diagnostics.Stopwatch]::StartNew()
}

function Complete-Phase {
    param([string]$Name, [Diagnostics.Stopwatch]$Timer)
    $Timer.Stop()
    $script:PhaseTimings[$Name] = $Timer.ElapsedMilliseconds
}

function Record-Deployment {
    param([string]$Status, [string]$CurrentPhase, [string]$Message = '')
    try {
        $Arguments = @($MemoryScript, 'record', '--status', $Status, '--phase', $CurrentPhase, '--duration-ms', $TotalTimer.ElapsedMilliseconds, '--requirement-id', $RequirementId, '--connection-mode', 'reused')
        if ($Message) { $Arguments += @('--error-type', 'DeploymentError', '--error-message', $Message) }
        & $Python @Arguments | Out-Null
    }
    catch { Write-Warning 'Deployment telemetry could not be recorded.' }
}

try {
    $Timer = Start-Phase -Name 'local_validation'
    $Tokens = $null
    $ParseErrors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($RemoteDeploy, [ref]$Tokens, [ref]$ParseErrors)
    if ($ParseErrors.Count) { throw "Remote deployer PowerShell parse failed: $($ParseErrors[0].Message)" }

    & $Node $BuildScript --source $BaselineHtml --output-dir $StageBuild --production-html $StageHtml
    if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' }
    foreach ($Leaf in $Expected.Keys) {
        $Path = if ($Leaf -eq 'frontend_dashboard_v3.server.html') { $StageHtml } else { Join-Path $StageBuild $Leaf }
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Expected build artifact missing: $Path" }
        $Hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        if ($Hash -ne $Expected[$Leaf]) { throw "Build artifact hash changed: $Leaf $Hash" }
    }
    & $Python -B -m pytest -q -p no:cacheprovider (Join-Path $Root 'tests\test_8093_frontend_performance_build.py') (Join-Path $Root 'tests\test_8093_http_static_stability.py') (Join-Path $Root 'tests\test_8093_http_static_stability_deployer.py')
    if ($LASTEXITCODE -ne 0) { throw 'Local frontend/backend contract tests failed.' }
    & $Python (Join-Path $Root 'tools\verify_8093_frontend_production_build.py') --source-html $BaselineHtml --production-html $StageHtml --output $VerifyOutput
    if ($LASTEXITCODE -ne 0) { throw 'Chromium 1366x768 core smoke failed.' }
    Complete-Phase -Name 'local_validation' -Timer $Timer

    $Timer = Start-Phase -Name 'session_ensure'
    $EnsureRaw = (& $Python $RemoteSession ensure --allow-agents-password --workdir $RemoteRoot | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH session ensure failed.' }
    $Ensure = $EnsureRaw | ConvertFrom-Json
    if (-not $Ensure.ok -or -not $Ensure.ssh_active) { throw 'Persistent SSH session is not active.' }
    Complete-Phase -Name 'session_ensure' -Timer $Timer

    $UploadArguments = @($RemoteSession, 'run', '--', '--no-profile', '--timeout', '90', '--workdir', $RemoteRoot, '--upload-only')
    foreach ($Upload in $Uploads) { $UploadArguments += @('--upload', $Upload) }
    $Timer = Start-Phase -Name 'staging_upload'
    $UploadRaw = (& $Python @UploadArguments | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed; production was not changed.' }
    $Upload = $UploadRaw | ConvertFrom-Json
    if (-not $Upload.ok -or $Upload.uncertain_execution) { throw 'Upload-only staging result was not trustworthy.' }
    Complete-Phase -Name 'staging_upload' -Timer $Timer

    if ($Upload.session_id -ne $Ensure.session_id -or $Upload.connection_id -ne $Ensure.connection_id) { throw 'SSH session identity changed during staging.' }

    $Timer = Start-Phase -Name 'guarded_deployment'
    $DeployRaw = (& $Python $RemoteSession run -- --no-profile --timeout 240 --workdir $RemoteRoot --script $RemoteDeploy | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Guarded deployment failed; inspect rollback evidence.' }
    $Deploy = $DeployRaw | ConvertFrom-Json
    if (-not $Deploy.ok -or $Deploy.uncertain_execution) { throw 'Guarded deployment result was not trustworthy.' }
    $JsonStart = $Deploy.stdout.IndexOf('{')
    $JsonEnd = $Deploy.stdout.LastIndexOf("`n[exit]")
    if ($JsonStart -lt 0 -or $JsonEnd -le $JsonStart) { throw 'Remote acceptance JSON was not found in the completed response.' }
    $RemoteResult = $Deploy.stdout.Substring($JsonStart, $JsonEnd - $JsonStart).Trim() | ConvertFrom-Json
    if (-not $RemoteResult.ok -or -not $RemoteResult.guard_paused -or -not $RemoteResult.guard_restored -or $RemoteResult.rollback_applied) {
        throw 'Remote acceptance fields did not prove a successful guarded deployment.'
    }
    Complete-Phase -Name 'guarded_deployment' -Timer $Timer

    if ($Deploy.session_id -ne $Ensure.session_id -or $Deploy.connection_id -ne $Ensure.connection_id) { throw 'SSH session identity changed during deployment.' }
    if ([int]$Deploy.request_count -le [int]$Upload.request_count) { throw 'SSH request counter did not increase.' }

    $Timer = Start-Phase -Name 'session_postcheck'
    $StatusRaw = (& $Python $RemoteSession status | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH postcheck failed.' }
    $Status = $StatusRaw | ConvertFrom-Json
    if (-not $Status.ok -or -not $Status.ssh_active) { throw 'Persistent SSH session is not healthy after deployment.' }
    if ($Status.session_id -ne $Ensure.session_id -or $Status.connection_id -ne $Ensure.connection_id) {
        throw 'Persistent SSH session identity changed after deployment.'
    }
    if ([int]$Status.request_count -lt [int]$Deploy.request_count) { throw 'Persistent SSH request counter moved backwards.' }
    Complete-Phase -Name 'session_postcheck' -Timer $Timer

    $TotalTimer.Stop()
    Record-Deployment -Status success -CurrentPhase total
    [pscustomobject]@{
        ok = $true
        requirement_id = $RequirementId
        session_id = $Ensure.session_id
        connection_id = $Ensure.connection_id
        request_count_before = $Ensure.request_count
        request_count_after = $Status.request_count
        total_duration_ms = $TotalTimer.ElapsedMilliseconds
        phase_duration_ms = $PhaseTimings
        remote_transport = $Deploy
        remote_result = $RemoteResult
    } | ConvertTo-Json -Depth 12
}
catch {
    $TotalTimer.Stop()
    Record-Deployment -Status failure -CurrentPhase $Phase -Message $_.Exception.Message
    throw
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
