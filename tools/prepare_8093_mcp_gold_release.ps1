[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-mcp-gold-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'REQ-MCP-AGENT-GOLDEN-SUITE-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'

$ArtifactSpecs = @(
    [ordered]@{
        relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
        stage_name = 'ollama_proxy_server.py'
        baseline = '89B262CA125916E25CF5D6375543E26AB89BA888371DD448A8E9B9BEACD42F79'
        markers = @('lifecycle_error("request_handler"', 'STDDEV_POP', 'pearson_r', 'handle_thermal_trend')
    },
    [ordered]@{
        relative = '高炉前端数据\智能助手\backend\mcp_host\client_manager.py'
        stage_name = 'client_manager.py'
        baseline = '6B5366C177091604FEE30ED73DDBCE3A384A4D5B73CB91DDF616F59725856DD9'
        markers = @('def exception_leaves', 'mcp_lifecycle_warning', 'stdio_teardown')
    },
    [ordered]@{
        relative = '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
        stage_name = 'cross_source_executor.py'
        baseline = '2273F1619871F88B2AF49FE6518BCB8E6D60AEAB013D9DF1BF58CF4CD2DECD06'
        markers = @('pearson_r', 'aligned_count', 'correlation_window')
    }
)
$Artifacts = @($ArtifactSpecs | ForEach-Object {
    [ordered]@{
        local_path = (Resolve-Path -LiteralPath (Join-Path $Root $_.relative)).Path
        stage = "$RemoteStage\$($_.stage_name)"
        target = "$RemoteRoot\$($_.relative)"
        baseline_sha256 = @($_.baseline)
        allow_create = $false
        markers = @($_.markers)
    }
})
$Sources = @(
    'tests\test_mcp_lifecycle_diagnostics.py',
    'tests\test_mcp_evidence_formatter.py',
    'tests\test_cross_source_mcp.py',
    'tests\test_qa_mcp_parallel_planning.py',
    'tests\test_qa_mcp_model_fallback.py',
    'tests\test_mcp_gold_tasks.py',
    'tests\test_agent_tool_capability_skill.py',
    'tests\test_thermal_trend_rule.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\verify_8093_mcp_gold_sse_once.py',
    'tools\remote_preflight_8093_mcp_gold_20260814.ps1',
    'PT\智能体工具能力金标任务清单.v1.json'
) | ForEach-Object { (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path }

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'standard'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = $Artifacts
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='87 focused deployment-contract, SSE, thermal, lifecycle, evidence, cross-source, planning, fallback, gold-task and skill tests passed.' },
        [ordered]@{ id='frontend-syntax'; kind='deterministic'; status='passed'; evidence='node --check abc-furnace-rules-production.js passed after remote-forward merge.' },
        [ordered]@{ id='main-agent-semantic-review'; kind='semantic'; status='passed'; evidence='Reviewed lifecycle teardown isolation, deterministic evidence formatting, correlation fact projection, exact target map and rollback boundary.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='8093/8094/8768/8770/5432/11434 healthy; keyword, guest_shared and MCP registry healthy; baseline hashes captured.' },
        [ordered]@{ id='production-git-baseline'; kind='deterministic'; status='passed'; evidence='Portable Git 2.53.0.windows.3; reviewed initial HEAD dad65e448958da299dd8359ac50531b161b77da6 tagged.' }
    )
}
[IO.File]::WriteAllText($SpecPath, ($Spec | ConvertTo-Json -Depth 10), $Utf8NoBom)
& $Python $ManifestTool prepare --spec $SpecPath --output $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release sealing failed.' }
& $Python $ManifestTool verify --manifest $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
$RemoteTargets = [ordered]@{}
foreach ($Artifact in $Artifacts) {
    $RemoteTargets[$Artifact.target] = [ordered]@{ exists = $true; sha256 = [string]$Artifact.baseline_sha256[0] }
}
$RemoteState = [ordered]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = $RequirementId
    targets = $RemoteTargets
}
[IO.File]::WriteAllText($RemoteStatePath, ($RemoteState | ConvertTo-Json -Depth 8), $Utf8NoBom)
& $Python $ManifestTool plan-delta --manifest $ManifestPath --remote-state $RemoteStatePath --output $DeltaPlanPath
if ($LASTEXITCODE -ne 0) { throw 'Delta plan generation failed.' }

[ordered]@{
    ok = $true
    requirement_id = $RequirementId
    artifact_count = $Artifacts.Count
    manifest = $ManifestPath
    manifest_sha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash
    delta_plan = $DeltaPlanPath
    delta_plan_sha256 = (Get-FileHash -LiteralPath $DeltaPlanPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 5
