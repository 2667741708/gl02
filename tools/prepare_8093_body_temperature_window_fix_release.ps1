[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-body-temperature-window-fix-20260814')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-MCP-BODY-WINDOW-ROLLING-DURATION-20260814'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$RemoteStatePath = Join-Path $OutputDirectory 'remote-state.json'
$DeltaPlanPath = Join-Path $OutputDirectory 'delta-plan.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_window_fix_20260814'
$Python = 'D:\ProgramData\anaconda3\python.exe'
$Relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$Target = "$RemoteRoot\$Relative"
$Baseline = '22A7B4B7252EBA907944525414A837901722D5509BEC832678DEF61A5F82ABAF'
$Artifact = [ordered]@{
    local_path = (Resolve-Path -LiteralPath (Join-Path $Root $Relative)).Path
    stage = "$RemoteStage\ollama_proxy_server.py"
    target = $Target
    baseline_sha256 = @($Baseline)
    allow_create = $false
    markers = @('duration_text = re.sub', 'rolling_window_minutes', 'qa_mcp_duration_minutes(duration_text)')
}
$Sources = @(
    'tests\test_body_temperature_layer_statistics.py',
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'docs\handoffs\2026-08-14-body-temperature-layer-statistics.md'
) | ForEach-Object { (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path }

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'quick'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = @($Artifact)
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='77 focused tests passed; one-hour total window remains 60 minutes when 15-minute rolling statistics are requested.' },
        [ordered]@{ id='production-observation'; kind='readonly_remote'; status='passed'; evidence='First guarded acceptance proved the composite tool but exposed a 15-minute total window due to duration token precedence.' },
        [ordered]@{ id='main-agent-semantic-review'; kind='semantic'; status='passed'; evidence='The fix removes rolling-window phrases only from total-window parsing; rolling_window_minutes remains unchanged.' }
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
    targets = [ordered]@{ $Target = [ordered]@{ exists = $true; sha256 = $Baseline } }
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
