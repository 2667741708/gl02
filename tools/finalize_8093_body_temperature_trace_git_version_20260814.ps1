[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$Head = '5d23c0e5e2456c597ad9ba5a9a8c03627c2c5ae9'
$Parent = '32130a518f77061633d2fdb32a7cd65033453fa3'
$ExecutionId = 'body-temperature-trace-20260814-2046-r3'
$RequirementId = 'REQ-QA-COMPOSITE-MCP-EXECUTION-TRACE-20260814'
$Tag = 'prod-8093/20260814-body_trace-5d23c0e5e245'
$Expected = [ordered]@{
    '高炉前端数据/frontend_dashboard_v3.server.html' = 'E63D80BEAB1AF72CD0650252881FEA70E9831D26CF0762BB97D03735A45B6B1A'
    '高炉前端数据/智能助手/backend/ollama_proxy_server.py' = '3F46FD86D458EA73B7060841BBCB6C017E7521E1F28A39651700965C997C59C2'
    '高炉前端数据/智能助手/backend/mcp_host/domain_router.py' = '92C8015FE14A26DD48B86D2CBE6C612C28F054F4EE06A284D25EC0CFE06F886D'
}

function Get-PortPid {
    param([int]$Port)
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

function Get-RuntimeSnapshot {
    $Result = [ordered]@{}
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434, 8892)) {
        $Result[[string]$Port] = Get-PortPid -Port $Port
    }
    return $Result
}

if ((Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString() -ne 'Running') {
    throw '8093 service is not Running.'
}
$Before = Get-RuntimeSnapshot
$CurrentHead = (& $GitExe -C $Root rev-parse HEAD | Out-String).Trim()
if ($CurrentHead -ne $Head) { throw "Unexpected production HEAD: $CurrentHead" }
$CurrentParent = (& $GitExe -C $Root rev-parse "$Head^" | Out-String).Trim()
if ($CurrentParent -ne $Parent) { throw 'Production commit parent changed.' }
$Status = @(& $GitExe -C $Root status --porcelain --untracked-files=no | Where-Object { $_ })
if ($Status.Count -ne 0) { throw "Production worktree is not clean: $($Status -join '; ')" }

$CommitPaths = @(& $GitExe -C $Root diff-tree --no-commit-id --name-only -r $Head | Where-Object { $_ })
$CommitPaths = @($CommitPaths | ForEach-Object { $_ -replace '\\', '/' } | Sort-Object -Unique)
$ExpectedPaths = @($Expected.Keys | Sort-Object -Unique)
if (Compare-Object -ReferenceObject $ExpectedPaths -DifferenceObject $CommitPaths) {
    throw "Commit path set is not exact: $($CommitPaths -join ', ')"
}
foreach ($Entry in $Expected.GetEnumerator()) {
    $Path = Join-Path $Root ($Entry.Key -replace '/', '\')
    $Hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($Hash -ne $Entry.Value) { throw "Committed file hash drift: $($Entry.Key)" }
}

$ExistingTag = (& $GitExe -C $Root tag --list $Tag | Out-String).Trim()
if ($ExistingTag) {
    $TaggedHead = (& $GitExe -C $Root rev-list -n 1 $Tag | Out-String).Trim()
    if ($TaggedHead -ne $Head) { throw 'Existing production tag points to another commit.' }
} else {
    & $GitExe -C $Root tag -a $Tag -m "Accepted 8093 body-temperature trace release $ExecutionId"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create production tag.' }
}

$Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 30
if (-not $Health.ok) { throw 'MCP health failed during Git finalization.' }
$After = Get-RuntimeSnapshot
foreach ($Port in $Before.Keys) {
    if ($Before[$Port] -ne $After[$Port]) { throw "Runtime PID changed during Git finalization: $Port" }
}

$ManifestPath = "F:\BF_Git\V4_8093_PREVIEW.release.$ExecutionId.json"
$Manifest = [ordered]@{
    schema = 'bf.8093-production-git-release-manifest.v1'
    requirement_id = $RequirementId
    execution_id = $ExecutionId
    created_at = (Get-Date).ToString('o')
    parent_head = $Parent
    head = $Head
    tag = $Tag
    commit_subject = (& $GitExe -C $Root log -1 --format=%s $Head | Out-String).Trim()
    reviewed_paths = $ExpectedPaths
    deployed_hashes = $Expected
    sensitive_scan_completed = $true
    sensitive_values_recorded = $false
    runtime_before = $Before
    runtime_after = $After
    service_restart_performed = $false
    resumed_after_partial_recorder = $true
}
[IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 8), $Utf8NoBom)

[ordered]@{
    ok = $true
    schema = 'bf.8093-production-git-release-finalize.v1'
    requirement_id = $RequirementId
    execution_id = $ExecutionId
    parent_head = $Parent
    head = $Head
    tag = $Tag
    reviewed_paths = $ExpectedPaths
    manifest_path = $ManifestPath
    runtime_before = $Before
    runtime_after = $After
} | ConvertTo-Json -Depth 8
