[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$PreparedManifest = '.tmp\hcz-rule-sensitivity-20260811\prepared-release.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-HCZ-RULE-SENSITIVITY-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteProbe = Join-Path $Root 'tools\remote_probe_hcz_rule_sensitivity_8093.ps1'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$PreparedManifest = (Resolve-Path -LiteralPath (Join-Path $Root $PreparedManifest)).Path
$Work = Join-Path $Root '.tmp\hcz-rule-sensitivity-20260811'
$RemoteStatePath = Join-Path $Work 'remote-state-live.json'
$DeltaPlanPath = Join-Path $Work 'delta-plan.json'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\hcz_rule_sensitivity_20260811'
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
    $Ensure = (& $Python $Session ensure --allow-agents-password --workdir $RemoteRoot | Out-String).Trim() | ConvertFrom-Json
    if (-not $Ensure.ok -or -not $Ensure.ssh_active) { throw 'Persistent SSH session is not active.' }

    $ProbeOuter = (& $Python $Session run -- --no-profile --timeout 120 --workdir $RemoteRoot --script $RemoteProbe | Out-String).Trim() | ConvertFrom-Json
    if (-not $ProbeOuter.ok -or $ProbeOuter.uncertain_execution) { throw 'Read-only production preflight was not trustworthy.' }
    if ($ProbeOuter.session_id -ne $Ensure.session_id -or $ProbeOuter.connection_id -ne $Ensure.connection_id) { throw 'SSH identity changed during preflight.' }
    $Probe = Convert-RemoteStdoutJson -Stdout $ProbeOuter.stdout
    if (-not $Probe.ok -or $Probe.service.status -ne 'Running' -or $Probe.page.status -ne 200) { throw 'Production preflight failed.' }

    $Targets = [ordered]@{}
    foreach ($Property in $Probe.files.PSObject.Properties) {
        $Targets[$Property.Name] = [ordered]@{
            exists = [bool]$Property.Value.exists
            sha256 = [string]$Property.Value.sha256
        }
    }
    [ordered]@{
        schema = 'bf.deploy.remote-state.v1'
        requirement_id = $RequirementId
        targets = $Targets
    } | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $RemoteStatePath -Encoding utf8

    & $Python $ManifestTool verify --manifest $PreparedManifest | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
    & $Python $ManifestTool plan-delta --manifest $PreparedManifest --remote-state $RemoteStatePath --output $DeltaPlanPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Delta planning failed.' }
    $Plan = Get-Content -LiteralPath $DeltaPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Changes = @($Plan.changes)
    if ($Changes.Count -eq 0) {
        [ordered]@{ ok = $true; requirement_id = $RequirementId; deployment_state = 'verified_noop'; production_changed = $false } | ConvertTo-Json
        return
    }
    if ($Changes.Count -gt 6) { throw "Unexpected delta count: $($Changes.Count)." }

    $UploadArgs = @($Session, 'run', '--', '--no-profile', '--timeout', '180', '--workdir', $RemoteRoot, '--upload-only')
    $UploadArgs += @('--upload', "$DeltaPlanPath=$RemoteStage\delta-plan.json")
    foreach ($Change in $Changes) {
        $UploadArgs += @('--upload', "$($Change.local_path)=$($Change.stage)")
    }
    $Upload = (& $Python @UploadArgs | Out-String).Trim() | ConvertFrom-Json
    if (-not $Upload.ok -or $Upload.uncertain_execution) { throw 'Upload-only staging was not trustworthy.' }
    if ($Upload.session_id -ne $Ensure.session_id -or $Upload.connection_id -ne $Ensure.connection_id) { throw 'SSH identity changed during staging.' }

    $DeployOuter = (& $Python $Session run -- --no-profile --timeout 420 --workdir $RemoteRoot --script $RemoteDeploy | Out-String).Trim() | ConvertFrom-Json
    if (-not $DeployOuter.ok -or $DeployOuter.uncertain_execution) { throw 'Guarded deployment was not trustworthy.' }
    if ($DeployOuter.session_id -ne $Ensure.session_id -or $DeployOuter.connection_id -ne $Ensure.connection_id) { throw 'SSH identity changed during deployment.' }
    $Acceptance = Convert-RemoteStdoutJson -Stdout $DeployOuter.stdout
    if (-not $Acceptance.ok -or -not $Acceptance.guard_restored -or $Acceptance.rollback_applied) { throw 'Remote acceptance did not prove a successful guarded deployment.' }

    $Status = (& $Python $Session status | Out-String).Trim() | ConvertFrom-Json
    if (-not $Status.ok -or -not $Status.ssh_active) { throw 'Persistent SSH postcheck failed.' }
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        deployment_state = 'deployed'
        notify_immediately = $true
        artifact_count_delta = $Changes.Count
        session_id = $Status.session_id
        connection_id = $Status.connection_id
        acceptance = $Acceptance
    } | ConvertTo-Json -Depth 10
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:PYTHONUTF8 = $PreviousPythonUtf8
}
