[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-mcp-gold003-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-MCP-GOLD003-MISSING-PTOP-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold003_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'
$RelativePath = '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'
$TargetPath = "$RemoteRoot\$RelativePath"
$BaselineHash = '1EEA98F9DBD639AE7D22EE6BF53A08FDF5167729FCBD29C9D1DF2BE728AA3DBC'
$CrossSourceRelativePath = '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
$CrossSourceTargetPath = "$RemoteRoot\$CrossSourceRelativePath"
$CrossSourceBaselineHash = 'E64CCDA2FAF7DA1BDAD21FD56CDCFD00F7BC0B0E9DBD02494A7C4D8622B0C9C6'

$Artifact = [ordered]@{
    local_path = (Resolve-Path -LiteralPath (Join-Path $Root $RelativePath)).Path
    stage = "$RemoteStage\domain_router.py"
    target = $TargetPath
    baseline_sha256 = @($BaselineHash)
    allow_create = $false
    markers = @('def select_mcp_servers', '"p_top"', 'GL02_TERMS')
}
$CrossSourceArtifact = [ordered]@{
    local_path = (Resolve-Path -LiteralPath (Join-Path $Root $CrossSourceRelativePath)).Path
    stage = "$RemoteStage\cross_source_executor.py"
    target = $CrossSourceTargetPath
    baseline_sha256 = @($CrossSourceBaselineHash)
    allow_create = $false
    markers = @('_CANONICAL_UNIT_FALLBACKS', '"P_top": "kPa"', 'latest.get("quality")')
}
$Sources = @(
    'tests\test_cross_source_mcp.py',
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
    artifacts = @($Artifact, $CrossSourceArtifact)
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='64 cross-source, parallel-planning and gold-contract tests passed.' },
        [ordered]@{ id='root-cause-review'; kind='semantic'; status='passed'; evidence='P_top canonical identifier was absent from GL02 domain triggers, so the exact mixed-source prompt attached IMES only.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='8093 and protected listeners healthy; production target clean at reviewed Git HEAD and baseline SHA-256.' }
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
        $TargetPath = [ordered]@{ exists = $true; sha256 = $BaselineHash }
        $CrossSourceTargetPath = [ordered]@{ exists = $true; sha256 = $CrossSourceBaselineHash }
    }
}
[IO.File]::WriteAllText($RemoteStatePath, ($RemoteState | ConvertTo-Json -Depth 8), $Utf8NoBom)
& $Python $ManifestTool plan-delta --manifest $ManifestPath --remote-state $RemoteStatePath --output $DeltaPlanPath
if ($LASTEXITCODE -ne 0) { throw 'Delta plan generation failed.' }

[ordered]@{
    ok = $true
    requirement_id = $RequirementId
    artifact_count = 2
    manifest = $ManifestPath
    manifest_sha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash
    delta_plan = $DeltaPlanPath
    delta_plan_sha256 = (Get-FileHash -LiteralPath $DeltaPlanPath -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 5
