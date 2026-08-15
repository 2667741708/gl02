[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-body-temperature-trace-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'REQ-QA-COMPOSITE-MCP-EXECUTION-TRACE-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_trace_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'

$FrontendRelative = '高炉前端数据\frontend_dashboard_v3.server.html'
$ProxyRelative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$RouterRelative = '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'
$FrontendTarget = "$RemoteRoot\$FrontendRelative"
$ProxyTarget = "$RemoteRoot\$ProxyRelative"
$RouterTarget = "$RemoteRoot\$RouterRelative"
$FrontendBaseline = '2D4F344C100FF37BDB82A32CAB47EAFF8D6C44A64EDDEC234A8902FC958F40F2'
$ProxyBaseline = '4C0421A8D9D31735D21138EA7B864629133A601031751CEE5CF653312F42D888'
$RouterBaseline = 'D33B33CBABD379B8D20C29AEA295E4C023874FCF7229A6296D6F3EF38798257F'

$Artifacts = @(
    [ordered]@{
        local_path = (Resolve-Path -LiteralPath (Join-Path $Root $FrontendRelative)).Path
        stage = "$RemoteStage\frontend_dashboard_v3.server.html"
        target = $FrontendTarget
        baseline_sha256 = @($FrontendBaseline)
        allow_create = $false
        markers = @('function QaExecutionTrace', '继续匿名使用', 'BFRecommendationContractLoadingV1')
    },
    [ordered]@{
        local_path = (Resolve-Path -LiteralPath (Join-Path $Root $ProxyRelative)).Path
        stage = "$RemoteStage\ollama_proxy_server.py"
        target = $ProxyTarget
        baseline_sha256 = @($ProxyBaseline)
        allow_create = $false
        markers = @('def qa_mcp_body_temperature_statistics_plan', 'def qa_mcp_public_trace', 'analysis_start')
    },
    [ordered]@{
        local_path = (Resolve-Path -LiteralPath (Join-Path $Root $RouterRelative)).Path
        stage = "$RemoteStage\domain_router.py"
        target = $RouterTarget
        baseline_sha256 = @($RouterBaseline)
        allow_create = $false
        markers = @('spoken_body_layer', 'body_temperature')
    }
)
$Sources = @(
    'tests\test_body_temperature_layer_statistics.py',
    'tests\test_qa_tool_execution_trace_ui.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\verify_8093_mcp_gold_sse_once.py',
    'logs\qa_composite_trace_local_standard_20260814_final\report.json'
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
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='63 focused MCP, routing, formatter and frontend contracts passed before sealing.' },
        [ordered]@{ id='release-candidate-viewports'; kind='browser'; status='passed'; evidence='QA route standard matrix passed 17/17 after feature completion.' },
        [ordered]@{ id='remote-authoritative-sync'; kind='readonly_remote'; status='passed'; evidence='Production HEAD 32130a5 guest UI recovery reviewed and preserved before sealing.' }
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
        $FrontendTarget = [ordered]@{ exists = $true; sha256 = $FrontendBaseline }
        $ProxyTarget = [ordered]@{ exists = $true; sha256 = $ProxyBaseline }
        $RouterTarget = [ordered]@{ exists = $true; sha256 = $RouterBaseline }
    }
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
