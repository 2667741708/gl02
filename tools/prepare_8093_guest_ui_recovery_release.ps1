[CmdletBinding()]
param(
    [string]$OutputDirectory = '.tmp\8093-guest-ui-recovery-20260814'
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
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = (Resolve-Path -LiteralPath (Join-Path $Root $OutputDirectory)).Path
$ArtifactPath = Join-Path $OutputDirectory 'frontend_dashboard_v3.server.html'
$ArtifactReportPath = Join-Path $OutputDirectory 'artifact-report.json'
$BrowserReportPath = Join-Path $OutputDirectory 'browser-standard.json'
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_guest_ui_recovery_20260814'
$Target = "$RemoteRoot\高炉前端数据\frontend_dashboard_v3.server.html"
$Baseline = '25DF40E5FACBA9CBF9DC37FCDA293F1C42970C5CAA9894F9F0A2757A91FCAD4E'
$Python = (Get-Command -Name python -ErrorAction Stop).Source

foreach ($Required in @($ArtifactPath, $ArtifactReportPath, $BrowserReportPath, $ManifestTool)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing prepared input: $Required" }
}
$ArtifactReport = Get-Content -LiteralPath $ArtifactReportPath -Raw -Encoding utf8 | ConvertFrom-Json
$BrowserReport = Get-Content -LiteralPath $BrowserReportPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($ArtifactReport.requirement_id -ne $RequirementId -or -not $ArtifactReport.excluded_unrelated_execution_trace) {
    throw 'Artifact report contract failed.'
}
if (-not $BrowserReport.ok -or [int]$BrowserReport.combinations -ne 17) {
    throw 'Standard browser matrix did not pass 17 combinations.'
}
if ((Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash -ne [string]$ArtifactReport.artifact_sha256) {
    throw 'Artifact bytes changed after browser validation.'
}

& $Python (Join-Path $Root '.tmp\run_8093_guest_recovery_tests.py')
if ($LASTEXITCODE -ne 0) { throw 'Focused guest recovery tests failed.' }
$PowerShellFiles = @(
    'tools\remote_probe_8093_guest_ui_recovery_state.ps1',
    'tools\remote_guarded_deploy_8093_guest_ui_recovery.ps1',
    'tools\remote_record_8093_guest_ui_git_version.ps1',
    'tools\prepare_8093_guest_ui_recovery_release.ps1'
)
foreach ($Relative in $PowerShellFiles) {
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $Root $Relative), [ref]$Tokens, [ref]$Errors
    )
    if ($Errors.Count) { throw "PowerShell parse failed: $Relative $($Errors[0].Message)" }
}

$Sources = @(
    $ArtifactPath,
    (Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'),
    (Join-Path $Root 'tools\build_8093_guest_frontend_recovery_artifact.py'),
    (Join-Path $Root 'tools\probe_8093_guest_browser.cjs'),
    (Join-Path $Root 'tools\verify_8093_guest_frontend_matrix.cjs'),
    (Join-Path $Root 'tools\remote_probe_8093_guest_ui_recovery_state.ps1'),
    (Join-Path $Root 'tools\remote_guarded_deploy_8093_guest_ui_recovery.ps1'),
    (Join-Path $Root 'tools\remote_record_8093_guest_ui_git_version.ps1'),
    (Join-Path $Root 'tools\prepare_8093_guest_ui_recovery_release.ps1'),
    (Join-Path $Root 'tests\test_qa_shared_guest_mode.py'),
    (Join-Path $Root 'tests\test_qa_session_login_bridge.py'),
    (Join-Path $Root 'tests\test_8093_guest_ui_recovery_deploy_scripts.py')
)
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'standard'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = @(
        [ordered]@{
            local_path = $ArtifactPath
            stage = "$RemoteStage\frontend_dashboard_v3.server.html"
            target = $Target
            baseline_sha256 = @($Baseline)
            allow_create = $false
            markers = @(
                'function QaGuestNav',
                '登录私有会话（可选）',
                '继续匿名使用',
                "accessMode === 'guest_shared'",
                'abc33-initial-question-20260814-r1'
            )
        }
    )
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='16 focused source and deployment tests passed.' },
        [ordered]@{ id='browser-standard'; kind='browser'; status='passed'; evidence='17/17 Chromium, Firefox and WebKit combinations passed; no chat POST.' },
        [ordered]@{ id='artifact-scope'; kind='deterministic'; status='passed'; evidence='Production baseline plus guest UI only; unrelated execution trace excluded.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='Anonymous bootstrap guest_shared; production dashboard baseline SHA-256 25DF40E5...; branch production-8093.' }
    )
}
[IO.File]::WriteAllText($SpecPath, ($Spec | ConvertTo-Json -Depth 10), $Utf8NoBom)
& $Python $ManifestTool prepare --spec $SpecPath --output $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release sealing failed.' }
& $Python $ManifestTool verify --manifest $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
[ordered]@{
    ok = $true
    requirement_id = $RequirementId
    manifest = $ManifestPath
    manifest_sha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash
    artifact_sha256 = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 5
