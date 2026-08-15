[CmdletBinding()]
param(
    [string]$OutputDirectory = '.tmp\8093-guest-conversation-recovery-20260814',
    [string]$ArtifactPath = '.tmp\8093-guest-conversation-recovery-20260814\ollama_proxy_server.py'
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
$OutputDirectory = Join-Path $Root $OutputDirectory
$ArtifactPath = (Resolve-Path -LiteralPath (Join-Path $Root $ArtifactPath)).Path
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_guest_conversation_recovery_20260814'
$Target = "$RemoteRoot\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$Baseline = '9BF931B3A14F3FBA96C62E9B8B1663E4DACEF10D2E0E0D8D23D625637E95AC1E'
$Python = (Get-Command -Name python -ErrorAction Stop).Source

& $Python -m py_compile $ArtifactPath (Join-Path $Root 'tools\verify_8093_mcp_gold_sse_once.py')
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
& $Python -m pytest tests/test_mcp_gold_deploy_scripts.py tests/test_qa_shared_guest_mode.py tests/test_qa_session_login_bridge.py tests/test_qa_mcp_model_fallback.py -q
if ($LASTEXITCODE -ne 0) { throw 'Focused regression tests failed.' }

$PowerShellFiles = @(
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\remote_record_8093_mcp_gold_git_version.ps1',
    'tools\remote_probe_8093_guest_conversation_recovery_state.ps1',
    'tools\prepare_8093_guest_conversation_recovery_release.ps1',
    'tools\deploy_8093_guest_conversation_recovery_20260814.ps1'
)
foreach ($Relative in $PowerShellFiles) {
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $Root $Relative), [ref]$Tokens, [ref]$Errors
    )
    if ($Errors.Count) { throw "PowerShell parse failed: $Relative $($Errors[0].Message)" }
}

$SourceRelatives = @(
    'tests\test_qa_shared_guest_mode.py',
    'tests\test_mcp_gold_deploy_scripts.py',
    'tools\verify_8093_mcp_gold_sse_once.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\remote_record_8093_mcp_gold_git_version.ps1',
    'tools\remote_probe_8093_guest_conversation_recovery_state.ps1',
    'tools\prepare_8093_guest_conversation_recovery_release.ps1',
    'tools\deploy_8093_guest_conversation_recovery_20260814.ps1',
    'docs\api_reference.md',
    'docs\requirements_traceability.md',
    'docs\test_reference.md',
    'docs\troubleshooting.md',
    'docs\handoffs\2026-08-14-8093-public-guest-conversation-recovery.md'
)
$Sources = @($ArtifactPath) + @($SourceRelatives | ForEach-Object {
    (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path
})
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'quick'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = @(
        [ordered]@{
            local_path = $ArtifactPath
            stage = "$RemoteStage\ollama_proxy_server.py"
            target = $Target
            baseline_sha256 = @($Baseline)
            allow_create = $false
            markers = @(
                'def qa_chat_conversation_id(',
                'ensure_shared_guest_conversation(conn, session)',
                'payload["conversation_id"] = conversation_id'
            )
        }
    )
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='25 focused QA, deployment and fallback tests passed.' },
        [ordered]@{ id='python-powershell-syntax'; kind='deterministic'; status='passed'; evidence='Python compile and PowerShell AST checks passed.' },
        [ordered]@{ id='luna-diff-review'; kind='semantic'; status='passed'; model='gpt-5.6-luna'; reasoning_effort='low'; evidence='PASS: guest IDs ignored, private owner validation retained, forbidden fields rejected before preparation.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='production-8093 HEAD 849d9554060f7c1252722e8394a9cb224ff13488; proxy baseline SHA-256 9BF931B3... downloaded and reviewed.' }
    )
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
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
