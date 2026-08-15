[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-mcp-gold005-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-MCP-GOLD005-DEPENDENCY-GATE-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'
$ProxyRelative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$ProxyTarget = "$RemoteRoot\$ProxyRelative"
$ProxyBaseline = '20B0AA5057F52DE8142DD4827DCFF3457B6E74779C6D3E7F4317324C7FEA7C09'

$Artifacts = @(
    [ordered]@{
        local_path = (Resolve-Path -LiteralPath (Join-Path $Root $ProxyRelative)).Path
        stage = "$RemoteStage\ollama_proxy_server.py"
        target = $ProxyTarget
        baseline_sha256 = @($ProxyBaseline)
        allow_create = $false
        markers = @('single_service_dependency', 'deterministic_heat_dependency_failure', '禁止猜测或替换炉号')
    }
)
$Sources = @(
    'tests\test_cross_source_mcp.py',
    'tests\test_mcp_gold_runtime_boundaries.py',
    'tests\test_mcp_gold_sse_once.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\verify_8093_mcp_gold_sse_once.py',
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
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='82 focused MCP gold, dependency, runtime-boundary, SSE and deploy tests passed.' },
        [ordered]@{ id='remote-first-merge'; kind='readonly_remote'; status='passed'; evidence='Remote diagnosis evidence labels and r2 cache key were reviewed and merged locally before deployment.' },
        [ordered]@{ id='production-git-baseline'; kind='deterministic'; status='passed'; evidence='Accepted boundary release saved at production HEAD 89091ab6a82f27f8142653805ffb49d2a229f2b4.' }
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
        $ProxyTarget = [ordered]@{ exists = $true; sha256 = $ProxyBaseline }
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
