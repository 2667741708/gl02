[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$SessionWorkdir = 'F:\高炉炼铁项目-real-sensor-v2_V3',
    [string]$PreparedManifest = '.tmp\diagnosis-ai-json-fix-20260811\prepared-release.json'
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

$RequirementId = 'BUG-8093-DIAGNOSIS-AI-JSON-DATETIME-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteProbe = Join-Path $Root 'tools\remote_probe_8093_diagnosis_ai_json_fix.ps1'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_8093_diagnosis_ai_json_fix.ps1'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$PreparedManifest = (Resolve-Path -LiteralPath (Join-Path $Root $PreparedManifest)).Path
$Work = Join-Path $Root '.tmp\diagnosis-ai-json-fix-20260811'
$RemoteStatePath = Join-Path $Work 'remote-state-live.json'
$DeltaPlanPath = Join-Path $Work 'delta-plan.json'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\diagnosis_ai_json_fix_20260811'
$Python = (Get-Command -Name python -ErrorAction Stop).Source

function Convert-RemoteStdoutJson {
    param([Parameter(Mandatory)][string]$Stdout)
    $Start = $Stdout.IndexOf('{')
    $End = $Stdout.LastIndexOf('}')
    if ($Start -lt 0 -or $End -le $Start) { throw 'Remote command did not emit a JSON object.' }
    return ($Stdout.Substring($Start, $End - $Start + 1) | ConvertFrom-Json)
}

foreach ($Path in @($Session, $RemoteProbe, $RemoteDeploy, $ManifestTool, $PreparedManifest)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file missing: $Path" }
}
New-Item -ItemType Directory -Path $Work -Force | Out-Null

$PreviousPythonPath = $env:PYTHONPATH
$PreviousPythonUtf8 = $env:PYTHONUTF8
$PythonLibs = Join-Path $Root '.tmp_pylibs'
if (Test-Path -LiteralPath $PythonLibs -PathType Container) { $env:PYTHONPATH = $PythonLibs }
$env:PYTHONUTF8 = '1'
try {
    $EnsureText = (& $Python $Session ensure --allow-agents-password --workdir $SessionWorkdir | Out-String).Trim()
    $Ensure = $EnsureText | ConvertFrom-Json
    if (-not $Ensure.ok -or -not $Ensure.ssh_active) { throw 'Persistent SSH session is not active.' }

    $ProbeText = (& $Python $Session run -- --no-profile --timeout 120 --workdir $RemoteRoot --script $RemoteProbe |
        Out-String).Trim()
    $ProbeOuter = $ProbeText | ConvertFrom-Json
    if (-not $ProbeOuter.ok -or $ProbeOuter.uncertain_execution) { throw 'Read-only preflight was not trustworthy.' }
    if ($ProbeOuter.session_id -ne $Ensure.session_id -or
        $ProbeOuter.connection_id -ne $Ensure.connection_id) {
        throw 'SSH identity changed during preflight.'
    }
    $Probe = Convert-RemoteStdoutJson -Stdout $ProbeOuter.stdout
    if (-not $Probe.ok -or $Probe.service.status -ne 'Running' -or
        $Probe.knowledge.retrieval_mode -ne 'keyword' -or $Probe.knowledge.evidence_count -lt 1) {
        throw 'Production connectivity or keyword retrieval preflight failed.'
    }

    $Targets = [ordered]@{}
    $Targets[$Probe.target.path] = [ordered]@{
        exists = [bool]$Probe.target.exists
        sha256 = [string]$Probe.target.sha256
    }
    [ordered]@{
        schema = 'bf.deploy.remote-state.v1'
        requirement_id = $RequirementId
        targets = $Targets
    } | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $RemoteStatePath -Encoding utf8

    & $Python $ManifestTool verify --manifest $PreparedManifest | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
    $PlanArguments = @(
        $ManifestTool
        'plan-delta'
        '--manifest', $PreparedManifest
        '--remote-state', $RemoteStatePath
        '--output', $DeltaPlanPath
    )
    & $Python @PlanArguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Delta planning failed.' }
    $Plan = Get-Content -LiteralPath $DeltaPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Changes = @($Plan.changes)
    if ($Changes.Count -eq 0) {
        [ordered]@{
            ok = $true
            requirement_id = $RequirementId
            deployment_state = 'verified_noop'
            production_changed = $false
        } | ConvertTo-Json
        return
    }
    if ($Changes.Count -ne 1) { throw "Unexpected delta count: $($Changes.Count)." }

    $UploadArguments = @(
        $Session
        'run'
        '--'
        '--no-profile'
        '--timeout'
        '180'
        '--workdir'
        $RemoteRoot
        '--upload-only'
        '--upload'
        "$DeltaPlanPath=$RemoteStage\delta-plan.json"
        '--upload'
        "$($Changes[0].local_path)=$($Changes[0].stage)"
    )
    $UploadText = (& $Python @UploadArguments | Out-String).Trim()
    $Upload = $UploadText | ConvertFrom-Json
    if (-not $Upload.ok -or $Upload.uncertain_execution) { throw 'Upload-only staging was not trustworthy.' }
    if ($Upload.session_id -ne $Ensure.session_id -or
        $Upload.connection_id -ne $Ensure.connection_id) {
        throw 'SSH identity changed during staging.'
    }

    $DeployText = (& $Python $Session run -- --no-profile --timeout 480 --workdir $RemoteRoot --script $RemoteDeploy |
        Out-String).Trim()
    $DeployOuter = $DeployText | ConvertFrom-Json
    if (-not $DeployOuter.ok -or $DeployOuter.uncertain_execution) {
        [ordered]@{
            phase = 'remote_guarded_deploy'
            ok = [bool]$DeployOuter.ok
            uncertain_execution = [bool]$DeployOuter.uncertain_execution
            error_type = [string]$DeployOuter.error_type
            error = [string]$DeployOuter.error
            stdout = [string]$DeployOuter.stdout
            stderr = [string]$DeployOuter.stderr
        } | ConvertTo-Json -Depth 5 | Write-Output
        throw 'Guarded deployment was not trustworthy.'
    }
    if ($DeployOuter.session_id -ne $Ensure.session_id -or
        $DeployOuter.connection_id -ne $Ensure.connection_id) {
        throw 'SSH identity changed during deployment.'
    }
    $Acceptance = Convert-RemoteStdoutJson -Stdout $DeployOuter.stdout
    if (-not $Acceptance.ok -or -not $Acceptance.guard_restored -or
        $Acceptance.rollback_applied -or $Acceptance.diagnosis_analysis.state -ne 'completed') {
        throw 'Remote acceptance did not prove a successful diagnosis-analysis repair.'
    }

    $StatusText = (& $Python $Session status | Out-String).Trim()
    $Status = $StatusText | ConvertFrom-Json
    if (-not $Status.ok -or -not $Status.ssh_active) { throw 'Persistent SSH postcheck failed.' }
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        deployment_state = 'deployed'
        production_changed = $true
        artifact_count_delta = 1
        session_id = $Status.session_id
        connection_id = $Status.connection_id
        acceptance = $Acceptance
    } | ConvertTo-Json -Depth 10
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:PYTHONUTF8 = $PreviousPythonUtf8
}
