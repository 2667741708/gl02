[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedParentHead,
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedProxySha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedClientManagerSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedCrossSourceSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedDomainRouterSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedDiagnosisReviewAssetSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedExtendedSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedCalculationCatalogSha256 = '',
    [ValidatePattern('^(?:[A-Fa-f0-9]{64})?$')]
    [string]$ExpectedFrontendSha256 = '',
    [ValidateSet('mcp_gold', 'gold003', 'boundary', 'proxy_only', 'body_stats', 'body_trace')]
    [string]$Profile = 'mcp_gold',
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe',
    [string]$RequirementId = 'REQ-MCP-AGENT-GOLDEN-SUITE-20260814'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$ServiceName = 'BFV4PreviewProxy8093'
$Mutex = $null
$LockTaken = $false
$RequiredPaths = @(if ($Profile -eq 'gold003') {
    @(
        '高炉前端数据/智能助手/backend/mcp_host/domain_router.py',
        '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py'
    )
} elseif ($Profile -eq 'boundary') {
    @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py'
    )
} elseif ($Profile -eq 'proxy_only') {
    @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py'
    )
} elseif ($Profile -eq 'body_stats') {
    @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py',
        '高炉前端数据/智能助手/mcp/bf_data_extended_mcp_server.py',
        '高炉前端数据/智能助手/mcp/catalog/calculation_tools.json'
    )
} elseif ($Profile -eq 'body_trace') {
    @(
        '高炉前端数据/frontend_dashboard_v3.server.html',
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/mcp_host/domain_router.py'
    )
} else {
    @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/mcp_host/client_manager.py',
        '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py'
    )
})
$OptionalReviewedPaths = @(
    '高炉前端数据/assets/abc-furnace-rules-production.js',
    '高炉前端数据/assets/bf-diagnosis-review-local.js',
    '高炉前端数据/智能助手/backend/abc_score_explanation.py',
    '高炉前端数据/智能助手/backend/config/thermal_trend_rule.v1.json'
)
$AllowedPaths = @($RequiredPaths + $OptionalReviewedPaths)
$ExpectedHashes = if ($Profile -eq 'gold003') {
    if (-not $ExpectedDomainRouterSha256 -or -not $ExpectedCrossSourceSha256) {
        throw 'gold003 profile requires domain-router and cross-source hashes.'
    }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedDomainRouterSha256.ToUpperInvariant()
        $RequiredPaths[1] = $ExpectedCrossSourceSha256.ToUpperInvariant()
    }
} elseif ($Profile -eq 'boundary') {
    if (-not $ExpectedProxySha256 -or -not $ExpectedCrossSourceSha256) {
        throw 'boundary profile requires proxy and cross-source hashes.'
    }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedProxySha256.ToUpperInvariant()
        $RequiredPaths[1] = $ExpectedCrossSourceSha256.ToUpperInvariant()
    }
} elseif ($Profile -eq 'proxy_only') {
    if (-not $ExpectedProxySha256) { throw 'proxy_only profile requires ExpectedProxySha256.' }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedProxySha256.ToUpperInvariant()
    }
} elseif ($Profile -eq 'body_stats') {
    if (-not $ExpectedProxySha256 -or -not $ExpectedCrossSourceSha256 -or -not $ExpectedExtendedSha256 -or -not $ExpectedCalculationCatalogSha256) {
        throw 'body_stats profile requires proxy, cross-source, extended MCP and calculation-catalog hashes.'
    }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedProxySha256.ToUpperInvariant()
        $RequiredPaths[1] = $ExpectedCrossSourceSha256.ToUpperInvariant()
        $RequiredPaths[2] = $ExpectedExtendedSha256.ToUpperInvariant()
        $RequiredPaths[3] = $ExpectedCalculationCatalogSha256.ToUpperInvariant()
    }
} elseif ($Profile -eq 'body_trace') {
    if (-not $ExpectedFrontendSha256 -or -not $ExpectedProxySha256 -or -not $ExpectedDomainRouterSha256) {
        throw 'body_trace profile requires frontend, proxy and domain-router hashes.'
    }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedFrontendSha256.ToUpperInvariant()
        $RequiredPaths[1] = $ExpectedProxySha256.ToUpperInvariant()
        $RequiredPaths[2] = $ExpectedDomainRouterSha256.ToUpperInvariant()
    }
} else {
    if (-not $ExpectedProxySha256 -or -not $ExpectedClientManagerSha256) {
        throw 'mcp_gold profile requires proxy and client-manager hashes.'
    }
    [ordered]@{
        $RequiredPaths[0] = $ExpectedProxySha256.ToUpperInvariant()
        $RequiredPaths[1] = $ExpectedClientManagerSha256.ToUpperInvariant()
        $RequiredPaths[2] = $ExpectedCrossSourceSha256.ToUpperInvariant()
    }
}
if ($ExpectedDiagnosisReviewAssetSha256) {
    $ExpectedHashes['高炉前端数据/assets/bf-diagnosis-review-local.js'] = $ExpectedDiagnosisReviewAssetSha256.ToUpperInvariant()
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
    $Rows = [ordered]@{}
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434, 8892)) {
        $Rows[[string]$Port] = Get-PortPid -Port $Port
    }
    return $Rows
}

function Get-ChangedPaths {
    $Rows = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read production Git status.' }
    $Paths = @()
    foreach ($Row in $Rows) {
        if ($Row.Length -lt 4) { throw "Unexpected Git status row: $Row" }
        $Path = $Row.Substring(3).Trim('"') -replace '\\', '/'
        if ($Path.Contains(' -> ')) { $Path = ($Path -split ' -> ')[-1].Trim('"') }
        $Paths += $Path
    }
    return @($Paths | Sort-Object -Unique)
}

function Assert-SensitiveScan {
    param([string[]]$Paths)
    $Patterns = @(
        '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
        '(?i)(password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*["''][^"'']{4,}["'']',
        '(?i)(postgres(?:ql)?|mysql|mssql)://[^:/\s]+:[^@/\s]+@',
        '(?i)Host\s*=\s*[^;]+;[^\r\n]*(Password|Pwd)\s*=\s*[^;\r\n]+'
    )
    foreach ($Path in $Paths) {
        $FullPath = Join-Path $Root ($Path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) { throw "Version target missing: $Path" }
        $Text = Get-Content -LiteralPath $FullPath -Raw -Encoding utf8
        foreach ($Pattern in $Patterns) {
            if ($Text -match $Pattern) { throw "Sensitive scan rejected reviewed path: $Path" }
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) { throw 'Portable Git is missing.' }
    if ((Get-Service -Name $ServiceName).Status.ToString() -ne 'Running') { throw '8093 service is not Running.' }
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if (-not $Before[[string]$Port]) { throw "Required listener missing before Git version save: $Port" }
    }
    $Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $Head -ne $ExpectedParentHead) { throw "Unexpected production Git HEAD: $Head" }

    foreach ($Entry in $ExpectedHashes.GetEnumerator()) {
        $FullPath = Join-Path $Root ($Entry.Key -replace '/', '\')
        $Actual = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash
        if ($Actual -ne $Entry.Value) { throw "Deployed hash drift before Git save: $($Entry.Key)" }
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) { throw 'Production maintenance mutex is busy.' }

    $ChangedBefore = Get-ChangedPaths
    foreach ($Path in $RequiredPaths) {
        if ($ChangedBefore -notcontains $Path) { throw "Deployed target is not recorded as changed: $Path" }
    }
    foreach ($Path in $ChangedBefore) {
        if ($AllowedPaths -notcontains $Path) { throw "Unreviewed production change blocks Git version save: $Path" }
    }
    Assert-SensitiveScan -Paths $ChangedBefore

    foreach ($Path in $RequiredPaths) {
        & $GitExe -C $Root add -- $Path
        if ($LASTEXITCODE -ne 0) { throw "Failed to stage reviewed production path: $Path" }
    }
    $Staged = @(& $GitExe -C $Root diff --cached --name-only --diff-filter=ACMRTUXB 2>$null | Where-Object { $_ })
    $Staged = @($Staged | ForEach-Object { $_ -replace '\\', '/' } | Sort-Object -Unique)
    if (Compare-Object -ReferenceObject $RequiredPaths -DifferenceObject $Staged) {
        throw 'Staged path set does not exactly match the reviewed change set.'
    }

    $CommitSubject = "release: MCP golden fixes $Profile [$RequirementId] [$ExecutionId]"
    & $GitExe -C $Root commit -m $CommitSubject
    if ($LASTEXITCODE -ne 0) { throw 'Failed to commit accepted production version.' }
    $NewHead = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $NewHead -notmatch '^[a-f0-9]{40}$' -or $NewHead -eq $ExpectedParentHead) {
        throw 'Production Git HEAD did not advance after commit.'
    }
    $ActualParent = (& $GitExe -C $Root rev-parse "$NewHead^" 2>$null | Out-String).Trim()
    if ($ActualParent -ne $ExpectedParentHead) { throw 'Production commit parent is not the reviewed baseline.' }
    $Remaining = @(Get-ChangedPaths)
    $ExpectedRemaining = @($ChangedBefore | Where-Object { $RequiredPaths -notcontains $_ } | Sort-Object -Unique)
    if (Compare-Object -ReferenceObject $ExpectedRemaining -DifferenceObject $Remaining) {
        throw "Production tree changed during Git save: $($Remaining -join ', ')"
    }

    $Tag = "prod-8093/20260814-$Profile-$($NewHead.Substring(0, 12))"
    & $GitExe -C $Root tag -a $Tag -m "Accepted 8093 MCP golden release $ExecutionId"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to tag accepted production version.' }

    $Health = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 30
    if (-not $Health.ok) { throw 'MCP health failed after Git version save.' }
    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434, 8892)) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) {
            throw "Runtime PID changed while saving Git version: port=$Port"
        }
    }

    $ManifestPath = "F:\BF_Git\V4_8093_PREVIEW.release.$ExecutionId.json"
    $Manifest = [ordered]@{
        schema = 'bf.8093-production-git-release-manifest.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        created_at = (Get-Date).ToString('o')
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        commit_subject = $CommitSubject
        reviewed_paths = $ChangedBefore
        deployed_hashes = $ExpectedHashes
        sensitive_scan_completed = $true
        sensitive_values_recorded = $false
        runtime_before = $Before
        runtime_after = $After
        service_restart_performed = $false
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 8), $Utf8NoBom)

    [ordered]@{
        ok = $true
        schema = 'bf.8093-production-git-release-save.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        reviewed_paths = $ChangedBefore
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
    } | ConvertTo-Json -Depth 8
} finally {
    if ($LockTaken -and $Mutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
