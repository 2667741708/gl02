[CmdletBinding()]
param(
    [string]$OutputDirectory = '.tmp\8093-body-temperature-answer-integrity-20260814',
    [string]$ArtifactPath = '.tmp\8093-body-temperature-answer-integrity-remote-review\ollama_proxy_server.remote.py'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-MCP-BODY-STATS-ANSWER-INTEGRITY-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_answer_integrity_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'
$Relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$Target = "$RemoteRoot\$Relative"
$Baseline = '9BF931B3A14F3FBA96C62E9B8B1663E4DACEF10D2E0E0D8D23D625637E95AC1E'
$ProxyArtifact = [ordered]@{
    local_path = (Resolve-Path -LiteralPath (Join-Path $Root $ArtifactPath)).Path
    stage = "$RemoteStage\ollama_proxy_server.py"
    target = $Target
    baseline_sha256 = @($Baseline)
    allow_create = $false
    markers = @(
        'layer_statistics_scope',
        'point_detail_intent',
        'body_temperature_statistics_result_invalid',
        'if name == "gl02ext__query_body_temperature_statistics"'
    )
}
$RouterRelative = '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'
$RouterTarget = "$RemoteRoot\$RouterRelative"
$RouterBaseline = 'D33B33CBABD379B8D20C29AEA295E4C023874FCF7229A6296D6F3EF38798257F'
$RouterArtifact = [ordered]@{
    local_path = (Resolve-Path -LiteralPath (Join-Path $Root $RouterRelative)).Path
    stage = "$RemoteStage\domain_router.py"
    target = $RouterTarget
    baseline_sha256 = @($RouterBaseline)
    allow_create = $false
    markers = @('spoken_body_layer', 'body_temperature = _contains_any')
}
$Sources = @(
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\abc_score_explanation.py',
    'tests\test_body_temperature_layer_statistics.py',
    'tests\test_abc_score_explanation.py',
    'tests\test_mcp_gold_deploy_scripts.py',
    'tools\verify_8093_body_temperature_answer_integrity_artifact.py',
    'tools\probe_body_temperature_statistics_mcp.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'docs\error_traceability.md',
    'docs\handoffs\2026-08-14-body-temperature-layer-statistics.md'
) | ForEach-Object { (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path }

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'quick'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = @($ProxyArtifact, $RouterArtifact)
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='116 related MCP, QA, domain routing, DAG precedence, evidence, frontend-sync and deployment contract tests passed.' },
        [ordered]@{ id='direct-composite-mcp'; kind='readonly_database'; status='passed'; evidence='Local direct MCP read returned 7 layers and 3248 rows in 2520.9 ms with source bf_sensor.one_minute_values; no model or QA router used.' },
        [ordered]@{ id='remote-git-gate'; kind='readonly_remote'; status='passed'; evidence='production-8093 HEAD 849d9554060f7c1252722e8394a9cb224ff13488; no staged changes. Three tracked production deltas were reviewed: ABC frontend, A/B/C score explanation, and proxy SHA-256 9BF931B3....' },
        [ordered]@{ id='remote-baseline-integration'; kind='semantic'; status='passed'; evidence='Artifact is based on exact remote SHA-256 9BF931B3... and preserves the remote build_score_explanation A/B/C feature while adding only the reviewed body-statistics route.' },
        [ordered]@{ id='main-agent-semantic-review'; kind='semantic'; status='passed'; evidence='Composite JSON remains complete only on the deterministic route; per-position output is authoritative and formatter failure is fail-closed without LLM arithmetic.' }
    )
}
[IO.File]::WriteAllText($SpecPath, ($Spec | ConvertTo-Json -Depth 10), $Utf8NoBom)
& $Python $ManifestTool prepare --spec $SpecPath --output $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release sealing failed.' }
& $Python $ManifestTool verify --manifest $ManifestPath
if ($LASTEXITCODE -ne 0) { throw 'Prepared release verification failed.' }
$RemoteState = [ordered]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = $RequirementId
    targets = [ordered]@{
        $Target = [ordered]@{ exists = $true; sha256 = $Baseline }
        $RouterTarget = [ordered]@{ exists = $true; sha256 = $RouterBaseline }
    }
}
[IO.File]::WriteAllText($RemoteStatePath, ($RemoteState | ConvertTo-Json -Depth 8), $Utf8NoBom)
& $Python $ManifestTool plan-delta --manifest $ManifestPath --remote-state $RemoteStatePath --output $DeltaPlanPath
if ($LASTEXITCODE -ne 0) { throw 'Delta plan generation failed.' }
[ordered]@{
    ok = $true
    requirement_id = $RequirementId
    manifest_sha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash
    delta_plan_sha256 = (Get-FileHash -LiteralPath $DeltaPlanPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 5
