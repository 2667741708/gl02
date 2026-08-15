[CmdletBinding()]
param([string]$OutputDirectory = '.tmp\8093-mcp-parallel-guest-20260813')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-8093-MCP-PARALLEL-5-AND-GUEST-DEPLOY-20260813'
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$OutputDirectory = Join-Path $Root $OutputDirectory
$SpecPath = Join-Path $OutputDirectory 'release-spec.json'
$ManifestPath = Join-Path $OutputDirectory 'prepared-release.json'
$ManifestTool = Join-Path $Root '.codex\skills\deploy-8093-guarded-update\scripts\release_manifest.py'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_stage'
$Python = 'D:\ProgramData\anaconda3\python.exe'
$BaselineHashes = @{
    '高炉前端数据\frontend_dashboard_v3.server.html' = 'E507DB204E1A7FAF4272C1C33D1CDB1FA7F4151F6782FBD214CAEB6DE32E1C37'
    '高炉前端数据\assets\abc-furnace-rules-production.js' = 'EBD128560FDDC8078C635B009025747462A58C2C1FA995901B911E2E84EB911B'
    '高炉前端数据\智能助手\backend\abc_score_explanation.py' = '55A43F7C06E4E30F4A3A5EBAC068402C0806F05182BE7F21B04E2281A403BDC2'
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py' = '081D27402180FE76D7526CD20F018A86969F53A0F152F8A3E85AFA78D1C93473'
    '高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql' = '94F88A0D24FF7C5E6BC2B9D0703837D3DFBCC19A98748E11182CA3A724B3CA36'
    '高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql' = 'E8A966E410AC48AA1E783D158847F81253596698BF261E3818E8756C681840E6'
}

$ArtifactSpecs = @(
    @('高炉前端数据\frontend_dashboard_v3.server.html', 'frontend_dashboard_v3.server.html', @('QaGuestNav', 'guest_shared')),
    @('高炉前端数据\assets\abc-furnace-rules-production.js', 'abc-furnace-rules-production.js', @('FIX-8093-A-SCORE-DEDUCTION-R2-20260813')),
    @('高炉前端数据\智能助手\backend\abc_score_explanation.py', 'abc_score_explanation.py', @('FIX-8093-A-SCORE-DEDUCTION-R2-20260813')),
    @('高炉前端数据\智能助手\backend\ollama_proxy_server.py', 'ollama_proxy_server.py', @('qa_mcp_execute_parallel_batch', 'model_planner_parallel', 'QA_GUEST_ENABLED')),
    @('高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql', 'postgresql_assistant.sql', @('uq_qa_shared_guest_room')),
    @('高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql', '20260811_abc_contextual_assistant.sql', @('uq_qa_shared_guest_room'))
)
$Artifacts = @()
foreach ($Item in $ArtifactSpecs) {
    $Local = (Resolve-Path -LiteralPath (Join-Path $Root $Item[0])).Path
    $Artifacts += [ordered]@{
        local_path = $Local
        stage = "$RemoteStage\$($Item[1])"
        target = "$RemoteRoot\$($Item[0])"
        baseline_sha256 = @($BaselineHashes[$Item[0]])
        allow_create = $false
        markers = @($Item[2])
    }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Sources = @(
    'tests\test_qa_mcp_parallel_planning.py',
    'tests\test_qa_mcp_model_fallback.py',
    'tests\test_qa_shared_guest_mode.py',
    'tools\remote_preflight_8093_mcp_parallel_guest.ps1',
    'tools\remote_accept_abc33_contextual_assistant.ps1',
    'tools\remote_deploy_abc33_contextual_assistant_8093.ps1',
    'tools\stage_abc33_contextual_assistant_8093_package.ps1'
) | ForEach-Object { (Resolve-Path -LiteralPath (Join-Path $Root $_)).Path }

$Spec = [ordered]@{
    schema = 'bf.deploy.release-spec.v1'
    requirement_id = $RequirementId
    validation_tier = 'standard'
    production_root = $RemoteRoot
    sources = $Sources
    artifacts = $Artifacts
    validations = @(
        [ordered]@{ id='focused-tests'; kind='deterministic'; status='passed'; evidence='42 focused backend, guest, owner, deployment and MCP tests plus 1 A-score explanation test passed.' },
        [ordered]@{ id='python-syntax'; kind='deterministic'; status='passed'; evidence='ollama_proxy_server.py compiled.' },
        [ordered]@{ id='main-agent-semantic-review'; kind='semantic'; status='passed'; evidence='Cross-server parallel, same-server serial, stable transcript order, global five-call cap.' },
        [ordered]@{ id='remote-readonly-preflight'; kind='readonly_remote'; status='passed'; evidence='8093 and protected listeners healthy; live hashes collected; current anonymous bootstrap is 403.' }
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
    artifact_count = $Artifacts.Count
    manifest = $ManifestPath
} | ConvertTo-Json -Depth 5
