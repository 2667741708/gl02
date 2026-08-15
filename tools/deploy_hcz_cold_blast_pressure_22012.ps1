[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$PreparedManifest = '.tmp\hcz-cold-blast-pressure-20260811\prepared-release.json',
    [string]$RemoteStateJson = '.tmp\hcz-cold-blast-pressure-20260811\remote-state.json'
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

$RequirementId = 'REQ-HCZ-COLD-BLAST-PRESSURE-20260811'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_hcz_cold_blast_pressure_8093.ps1'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$PreparedManifest = (Resolve-Path -LiteralPath (Join-Path $Root $PreparedManifest)).Path
$RemoteStateJson = (Resolve-Path -LiteralPath (Join-Path $Root $RemoteStateJson)).Path
$DeltaPlan = Join-Path $Root '.tmp\hcz-cold-blast-pressure-20260811\delta-plan.json'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\hcz_cold_blast_pressure_20260811'
$Python = (Get-Command -Name python -ErrorAction Stop).Source

foreach ($Path in @($Session, $RemoteDeploy, $ManifestTool, $PreparedManifest, $RemoteStateJson)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required file missing: $Path" }
}

& $Python $ManifestTool verify --manifest $PreparedManifest | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
& $Python $ManifestTool plan-delta --manifest $PreparedManifest --remote-state $RemoteStateJson --output $DeltaPlan | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Delta planning failed.' }
$Plan = Get-Content -LiteralPath $DeltaPlan -Raw -Encoding UTF8 | ConvertFrom-Json
$Changes = @($Plan.changes)
if ($Changes.Count -eq 0) {
    [pscustomobject]@{ ok = $true; requirement_id = $RequirementId; deployment_state = 'verified_noop'; production_changed = $false } | ConvertTo-Json
    return
}
if ($Changes.Count -ne 1) { throw "Expected one configuration delta, received $($Changes.Count)." }

$PreviousPythonPath = $env:PYTHONPATH
$PythonLibs = Join-Path $Root '.tmp_pylibs'
if (Test-Path -LiteralPath $PythonLibs -PathType Container) { $env:PYTHONPATH = $PythonLibs }
try {
    $Ensure = (& $Python $Session ensure --allow-agents-password --workdir $RemoteRoot | Out-String).Trim() | ConvertFrom-Json
    if (-not $Ensure.ok -or -not $Ensure.ssh_active) { throw 'Persistent SSH session is not active.' }
    $UploadArgs = @(
        $Session, 'run', '--', '--no-profile', '--timeout', '90', '--workdir', $RemoteRoot, '--upload-only',
        '--upload', "$DeltaPlan=$RemoteStage\delta-plan.json",
        '--upload', "$($Changes[0].local_path)=$($Changes[0].stage)"
    )
    $Upload = (& $Python @UploadArgs | Out-String).Trim() | ConvertFrom-Json
    if (-not $Upload.ok -or $Upload.uncertain_execution) { throw 'Upload-only staging was not trustworthy.' }
    if ($Upload.session_id -ne $Ensure.session_id -or $Upload.connection_id -ne $Ensure.connection_id) { throw 'SSH identity changed during staging.' }
    $Deploy = (& $Python $Session run -- --no-profile --timeout 300 --workdir $RemoteRoot --script $RemoteDeploy | Out-String).Trim() | ConvertFrom-Json
    if (-not $Deploy.ok -or $Deploy.uncertain_execution) { throw 'Guarded deployment was not trustworthy.' }
    if ($Deploy.session_id -ne $Ensure.session_id -or $Deploy.connection_id -ne $Ensure.connection_id) { throw 'SSH identity changed during deployment.' }
    $Status = (& $Python $Session status | Out-String).Trim() | ConvertFrom-Json
    if (-not $Status.ok -or -not $Status.ssh_active) { throw 'Persistent SSH postcheck failed.' }
    [pscustomobject]@{
        ok = $true
        requirement_id = $RequirementId
        deployment_state = 'deployed'
        notify_immediately = $true
        artifact_count_delta = $Changes.Count
        session_id = $Status.session_id
        connection_id = $Status.connection_id
    } | ConvertTo-Json -Depth 4
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
