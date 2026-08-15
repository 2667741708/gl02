[CmdletBinding()]
param(
    [string]$PreparedManifest = '.tmp\8093-guest-conversation-recovery-20260814\prepared-release.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-8093-GUEST-CONVERSATION-RECOVERY-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PreparedManifest = (Resolve-Path -LiteralPath (Join-Path $Root $PreparedManifest)).Path
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_guest_conversation_recovery_20260814'
$RemoteState = Join-Path $Root '.tmp\8093-guest-conversation-recovery-20260814\remote-state.live.json'
$DeltaPlan = Join-Path $Root '.tmp\8093-guest-conversation-recovery-20260814\delta-plan.json'
$Controller = Join-Path $Root '.tmp\8093-guest-conversation-recovery-20260814\remote-controller.ps1'
$RemoteStatePath = "$StageRoot\remote-state.json"
$ExecutionId = "guest-conversation-recovery-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

& $Python $Session ensure --allow-agents-password --workdir $RemoteRoot
if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH session is unavailable.' }
& $Python $Session run -- --no-profile --timeout 60 --workdir $RemoteRoot --script (Join-Path $Root 'tools\remote_probe_8093_guest_conversation_recovery_state.ps1') --download "$RemoteStatePath=$RemoteState"
if ($LASTEXITCODE -ne 0) { throw 'Live remote-state probe failed.' }
& $Python $ManifestTool verify --manifest $PreparedManifest
if ($LASTEXITCODE -ne 0) { throw 'Prepared manifest changed; return to preparation.' }
& $Python $ManifestTool plan-delta --manifest $PreparedManifest --remote-state $RemoteState --output $DeltaPlan
if ($LASTEXITCODE -ne 0) { throw 'Delta planning failed.' }
$Plan = Get-Content -LiteralPath $DeltaPlan -Raw -Encoding utf8 | ConvertFrom-Json
$Changes = @($Plan.changes)
if ($Changes.Count -eq 0) {
    [ordered]@{ ok=$true; deployment_state='verified_noop'; requirement_id=$RequirementId } | ConvertTo-Json
    return
}
if ($Changes.Count -ne 1) { throw "Expected one backend artifact, actual=$($Changes.Count)" }
$State = Get-Content -LiteralPath $RemoteState -Raw -Encoding utf8 | ConvertFrom-Json
$ExpectedHead = [string]$State.production.git_head
$ExpectedHash = [string]$Changes[0].desired_sha256
$DeltaHash = (Get-FileHash -LiteralPath $DeltaPlan -Algorithm SHA256).Hash
$ControllerText = @"
[CmdletBinding()]
param()
`$ErrorActionPreference = 'Stop'
`$Deploy = '$StageRoot\remote_guarded_deploy_8093_mcp_gold.ps1'
`$Record = '$StageRoot\remote_record_8093_mcp_gold_git_version.ps1'
`$DeployText = (& `$Deploy -ExecutionId '$ExecutionId' -ExpectedManifestSha256 '$DeltaHash' -ExpectedGitHead '$ExpectedHead' -AcceptanceProfile 'guest_conversation_recovery' -RequirementId '$RequirementId' -StageRoot '$StageRoot' | Out-String).Trim()
if (`$LASTEXITCODE -ne 0) { throw 'Guarded deployment failed.' }
`$DeployRecord = `$DeployText | ConvertFrom-Json
if (-not `$DeployRecord.ok -or `$DeployRecord.rollback_applied -or -not `$DeployRecord.guard_restored) { throw 'Guarded deployment acceptance was not successful.' }
`$VersionText = (& `$Record -ExecutionId '$ExecutionId' -ExpectedParentHead '$ExpectedHead' -ExpectedProxySha256 '$ExpectedHash' -Profile 'proxy_only' -RequirementId '$RequirementId' | Out-String).Trim()
if (`$LASTEXITCODE -ne 0) { throw 'Production Git version save failed after accepted deployment.' }
`$VersionRecord = `$VersionText | ConvertFrom-Json
[ordered]@{ ok=`$true; deployment=`$DeployRecord; version=`$VersionRecord } | ConvertTo-Json -Depth 12
"@
[IO.File]::WriteAllText($Controller, $ControllerText, $Utf8NoBom)

$Uploads = @(
    "$DeltaPlan=$StageRoot\delta-plan.json",
    "$($Changes[0].local_path)=$($Changes[0].stage)",
    "$(Join-Path $Root 'tools\remote_guarded_deploy_8093_mcp_gold.ps1')=$StageRoot\remote_guarded_deploy_8093_mcp_gold.ps1",
    "$(Join-Path $Root 'tools\verify_8093_mcp_gold_sse_once.py')=$StageRoot\verify_8093_mcp_gold_sse_once.py",
    "$(Join-Path $Root 'tools\remote_record_8093_mcp_gold_git_version.ps1')=$StageRoot\remote_record_8093_mcp_gold_git_version.ps1"
)
$UploadArgs = @($Session, 'run', '--', '--no-profile', '--timeout', '90', '--workdir', $RemoteRoot, '--upload-only')
foreach ($Upload in $Uploads) { $UploadArgs += @('--upload', $Upload) }
& $Python @UploadArgs
if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed; production was not changed.' }
& $Python $Session run -- --no-profile --timeout 720 --workdir $RemoteRoot --script $Controller
if ($LASTEXITCODE -ne 0) { throw 'Guarded deployment or version save failed.' }
& $Python $Session status
