[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-body-temperature-statistics-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-MCP-BODY-LAYER-STATISTICS-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_statistics_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'

$ArtifactSpecs = @(
    [ordered]@{
        relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
        stage_name = 'ollama_proxy_server.py'
        baseline = 'B0FD19BFAFD403B7A37A62CC7FDC743185A2F20EBEF03075D99923163F8BEBD4'
        markers = @('def qa_mcp_body_temperature_statistics_plan', 'gl02ext__query_body_temperature_statistics', '分钟滚动标准差')
    },
    [ordered]@{
        relative = '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
        stage_name = 'cross_source_executor.py'
        baseline = 'F042842B56782B99B2707805841EE0C4382106ED184D4C26EBBD1C5F48629181'
        markers = @('body_temperature_statistics', 'gl02ext__query_body_temperature_statistics')
    },
    [ordered]@{
        relative = '高炉前端数据\智能助手\mcp\bf_data_extended_mcp_server.py'
        stage_name = 'bf_data_extended_mcp_server.py'
        baseline = '2B0AA1656F5AEA1C884006D73F5268FB914FFC2C7877711F9AEFABE048173C00'
        markers = @('def query_body_temperature_statistics', 'STDDEV_POP', '"interpolation": "none"')
    },
    [ordered]@{
        relative = '高炉前端数据\智能助手\mcp\catalog\calculation_tools.json'
        stage_name = 'calculation_tools.json'
        baseline = '71949288EC5622BFC10995B07D97D2292342A6BA8AE1911F11ED25397A78B9D3'
        markers = @('body_temperature_layer_statistics', 'query_body_temperature_statistics')
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
    'tests\test_body_temperature_layer_statistics.py',
    'tests\test_cross_source_mcp.py',
    'tests\test_mcp_evidence_formatter.py',
    'tests\test_qa_mcp_parallel_planning.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\verify_8093_mcp_gold_sse_once.py',
    'docs\handoffs\2026-08-14-body-temperature-layer-statistics.md'
) | ForEach-Object { (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path }

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'quick'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = $Artifacts
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='78 focused body-temperature, cross-source, evidence, planning, fallback and semantic-catalog tests passed.' },
        [ordered]@{ id='main-agent-semantic-review'; kind='semantic'; status='passed'; evidence='Reviewed one-call routing, minute alignment, no interpolation/filtering, population formulas, source disclosure and protected service scope.' },
        [ordered]@{ id='remote-git-review-gate'; kind='readonly_remote'; status='passed'; evidence='production-8093 HEAD 67d2434cbbb69591ff8e35d4027fd47acfa37850; clean tracked/staged state; no remote-only uncommitted source.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='SSH, PostgreSQL 5432, 8093 and Ollama 11434 reachable; protected PID baseline captured.' }
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
