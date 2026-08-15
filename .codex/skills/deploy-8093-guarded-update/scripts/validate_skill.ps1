$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This validator requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$SkillRoot = Split-Path -Parent $PSScriptRoot
$SkillFile = Join-Path $SkillRoot 'SKILL.md'
$ReferenceFile = Join-Path $SkillRoot 'references\project-contract.md'
$ProtectionReference = Join-Path $SkillRoot 'references\python-artifact-protection.md'
$PerformanceReference = Join-Path $SkillRoot 'references\deployment-performance-and-learning.md'
$RetentionReference = Join-Path $SkillRoot 'references\reusable-artifact-retention.md'
$ValidationReference = Join-Path $SkillRoot 'references\validation-tiers.md'
$TwoPhaseReference = Join-Path $SkillRoot 'references\two-phase-fast-deployment.md'
$RemoteGitReference = Join-Path $SkillRoot 'references\remote-git-bidirectional-sync.md'
$FailurePlaybook = Join-Path $SkillRoot 'references\learned-failure-playbook.json'
$MemoryScript = Join-Path $SkillRoot 'scripts\deployment_memory.py'
$ReleaseManifestScript = Join-Path $SkillRoot 'scripts\release_manifest.py'
$LocalTemplate = Join-Path $SkillRoot 'assets\deploy_8093_guarded_update.ps1.template'
$RemoteTemplate = Join-Path $SkillRoot 'assets\remote_guarded_deploy_8093.ps1.template'
$OpenAiFile = Join-Path $SkillRoot 'agents\openai.yaml'

foreach ($Path in @($SkillFile, $ReferenceFile, $ProtectionReference, $PerformanceReference, $RetentionReference, $ValidationReference, $TwoPhaseReference, $RemoteGitReference, $FailurePlaybook, $MemoryScript, $ReleaseManifestScript, $LocalTemplate, $RemoteTemplate, $OpenAiFile)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required skill artifact missing: $Path"
    }
}

$SkillText = Get-Content -LiteralPath $SkillFile -Raw -Encoding UTF8
$ReferenceText = Get-Content -LiteralPath $ReferenceFile -Raw -Encoding UTF8
$ProtectionText = Get-Content -LiteralPath $ProtectionReference -Raw -Encoding UTF8
$PerformanceText = Get-Content -LiteralPath $PerformanceReference -Raw -Encoding UTF8
$RetentionText = Get-Content -LiteralPath $RetentionReference -Raw -Encoding UTF8
$ValidationText = Get-Content -LiteralPath $ValidationReference -Raw -Encoding UTF8
$TwoPhaseText = Get-Content -LiteralPath $TwoPhaseReference -Raw -Encoding UTF8
$RemoteGitText = Get-Content -LiteralPath $RemoteGitReference -Raw -Encoding UTF8
$LocalText = Get-Content -LiteralPath $LocalTemplate -Raw -Encoding UTF8
$RemoteText = Get-Content -LiteralPath $RemoteTemplate -Raw -Encoding UTF8
$OpenAiText = Get-Content -LiteralPath $OpenAiFile -Raw -Encoding UTF8

foreach ($Token in @(
    'Global\BFV4PreviewProxy8093Deployment',
    'guard_paused=true',
    'guard_restored=true',
    'rollback_applied=false',
    'remote_22012_session.py run -- --script',
    'uncertain_execution=true',
    'python-artifact-protection.md',
    'verify_22012_persistent_ssh_reuse.ps1',
    'independent UTF-8 PowerShell file',
    'deployment_memory.py',
    'release_manifest.py',
    'learned-failure-playbook.json',
    'validation-tiers.md',
    'two-phase-fast-deployment.md',
    'bf.deploy.prepared-release.v1',
    'bf.deploy.delta-plan.v1',
    'gpt-5.6-luna',
    'notify_immediately',
    '.codex/skills/deploy-8093-guarded-update',
    'sync_deploy_8093_guarded_update_skill.ps1',
    'PublishProjectToGlobal',
    'reusable-artifact-retention.md',
    'OPS-22012-REUSABLE-ARTIFACT-RETENTION-20260812'
    'remote-git-bidirectional-sync.md'
    'deployed_version_record_failed'
)) {
    if (-not $SkillText.Contains($Token)) { throw "SKILL.md missing contract token: $Token" }
}
foreach ($Token in @(
    'BFV4PreviewProxy8093',
    'manage_22012_managed_services.ps1',
    '22012_BFV4PreviewProxy8093.json',
    'PowerShell 7',
    'protected_before'
)) {
    if (-not $ReferenceText.Contains($Token)) { throw "Project reference missing contract token: $Token" }
}
foreach ($Token in @('remote_22012_session.py', 'ensure', '--upload-only', '--script', 'production was not changed', 'status', 'PreparedManifest', 'RemoteStateJson', 'plan-delta', 'artifact_count_delta', 'verified_noop')) {
    if (-not $LocalText.Contains($Token)) { throw "Local template missing contract token: $Token" }
}
foreach ($Token in @('`.pyb`', '`.pyc`', '`.pyd`', 'Nuitka', 'Cython', 'reverse engineering impossible')) {
    if (-not $ProtectionText.Contains($Token)) { throw "Python protection reference missing contract token: $Token" }
}
foreach ($Token in @('five cold', 'five persistent-session', 'median and p90', 'candidate_review', 'two successful remediations')) {
    if (-not $PerformanceText.Contains($Token)) { throw "Performance/learning reference missing contract token: $Token" }
}
foreach ($Token in @('remote_22012_session.py', 'Playwright', 'storageState', 'LocalAppData', 'SHA-256', 'do not keep', 'fresh production-state check')) {
    if (-not $RetentionText.Contains($Token)) { throw "Retention reference missing contract token: $Token" }
}
foreach ($Token in @('quick', 'standard', 'full', '4', '17', '85', 'production')) {
    if (-not $ValidationText.Contains($Token)) { throw "Validation tier reference missing contract token: $Token" }
}
foreach ($Token in @('bf.deploy.release-spec.v1', 'bf.deploy.prepared-release.v1', 'bf.deploy.remote-state.v1', 'bf.deploy.delta-plan.v1', 'gpt-5.6-luna', 'low', 'concurrently', 'verified no-op')) {
    if (-not $TwoPhaseText.Contains($Token)) { throw "Two-phase reference missing contract token: $Token" }
}
foreach ($Token in @('git pull', 'status --porcelain=v2', 'git add -A', 'rollback_applied=false', 'production_git_commit', 'production_version_ref', 'deployed_version_record_failed', 'external remote push')) {
    if (-not $RemoteGitText.Contains($Token)) { throw "Remote Git reference missing contract token: $Token" }
}
$Playbook = Get-Content -LiteralPath $FailurePlaybook -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Playbook.schema -ne 'bf.deploy.reviewed-failure-playbook.v1' -or $Playbook.rules.Count -lt 5) {
    throw 'Reviewed failure playbook is invalid or incomplete.'
}
if ($LocalText.IndexOf('--upload-only', [StringComparison]::Ordinal) -gt $LocalText.IndexOf('--script', [StringComparison]::Ordinal)) {
    throw 'Local template must pre-stage before executing the remote payload.'
}
foreach ($Token in @(
    'Global\BFV4PreviewProxy8093Deployment',
    'BaselineHashes',
    'Get-FileHash',
    'bf.deploy.delta-plan.v1',
    'DesiredHash',
    'artifact_count_delta',
    'Stop-8093',
    'Start-8093',
    'rollback_applied',
    'finally',
    '8094, 8768, 8770, 5432, 11434',
    'Assert-BelowRoot'
)) {
    if (-not $RemoteText.Contains($Token)) { throw "Remote template missing contract token: $Token" }
}
if (-not $OpenAiText.Contains('$deploy-8093-guarded-update')) {
    throw 'agents/openai.yaml default prompt does not invoke the skill.'
}
if (-not $OpenAiText.Contains('allow_implicit_invocation: true')) {
    throw 'agents/openai.yaml must allow implicit invocation for 8093 updates.'
}

$Python = (Get-Command -Name python -ErrorAction Stop).Source
& $Python $MemoryScript --self-test | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'deployment_memory.py self-test failed.'
}
& $Python $ReleaseManifestScript --self-test | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'release_manifest.py self-test failed.'
}

$ParseErrors = @()
[System.Management.Automation.Language.Parser]::ParseFile($LocalTemplate, [ref]$null, [ref]$ParseErrors) | Out-Null
if ($ParseErrors.Count -gt 0) {
    throw "Local PowerShell template parse failed: $($ParseErrors[0].Message)"
}
$ParseErrors = @()
[System.Management.Automation.Language.Parser]::ParseFile($RemoteTemplate, [ref]$null, [ref]$ParseErrors) | Out-Null
if ($ParseErrors.Count -gt 0) {
    throw "Remote PowerShell template parse failed: $($ParseErrors[0].Message)"
}

[pscustomobject]@{
    ok = $true
    skill = 'deploy-8093-guarded-update'
    powershell = $PSVersionTable.PSVersion.ToString()
    parsed_templates = 2
    deterministic_scripts = 2
    remote_write_performed = $false
} | ConvertTo-Json -Depth 3
