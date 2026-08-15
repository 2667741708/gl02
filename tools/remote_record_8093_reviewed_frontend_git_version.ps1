[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedParentHead,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedAssetSha256,
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe',
    [string]$RequirementId = 'OPS-22012-GIT-BASELINE-20260814'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$RelativePath = '高炉前端数据/assets/abc-furnace-rules-production.js'
$FullPath = Join-Path $Root ($RelativePath -replace '/', '\')
$Mutex = $null
$LockTaken = $false

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
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        $Rows[[string]$Port] = Get-PortPid -Port $Port
    }
    return $Rows
}

try {
    if ((Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString() -ne 'Running') {
        throw '8093 service is not Running.'
    }
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if (-not $Before[[string]$Port]) { throw "Required listener missing: $Port" }
    }
    $Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    if ($Head -ne $ExpectedParentHead) { throw "Unexpected production Git HEAD: $Head" }
    if ((Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash -ne $ExpectedAssetSha256.ToUpperInvariant()) {
        throw 'Reviewed frontend asset hash drifted before Git save.'
    }
    $Text = Get-Content -LiteralPath $FullPath -Raw -Encoding utf8
    $SensitivePatterns = @(
        '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
        '(?i)(password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*["''][^"'']{4,}["'']',
        '(?i)(postgres(?:ql)?|mysql|mssql)://[^:/\s]+:[^@/\s]+@'
    )
    foreach ($Pattern in $SensitivePatterns) {
        if ($Text -match $Pattern) { throw 'Sensitive scan rejected the reviewed frontend asset.' }
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try { $LockTaken = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $LockTaken = $true }
    if (-not $LockTaken) { throw 'Production maintenance mutex is busy.' }

    $Status = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
    if ($Status.Count -ne 1 -or ($Status[0].Substring(3) -replace '\\', '/') -ne $RelativePath) {
        throw "Exact reviewed frontend status required: $($Status -join ', ')"
    }
    if ($Status[0].Substring(0, 1) -ne ' ') { throw 'Pre-existing staged production change blocks save.' }

    & $GitExe -C $Root add -- $RelativePath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage reviewed frontend asset.' }
    $Staged = @(& $GitExe -C $Root diff --cached --name-only 2>$null | Where-Object { $_ })
    if ($Staged.Count -ne 1 -or ($Staged[0] -replace '\\', '/') -ne $RelativePath) {
        throw 'Staged path is not the exact reviewed frontend asset.'
    }
    $Subject = "sync: reviewed 8093 frontend production update [$RequirementId] [$ExecutionId]"
    & $GitExe -C $Root commit -m $Subject
    if ($LASTEXITCODE -ne 0) { throw 'Failed to commit reviewed frontend update.' }
    $NewHead = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    $Parent = (& $GitExe -C $Root rev-parse "$NewHead^" 2>$null | Out-String).Trim()
    if ($NewHead -notmatch '^[a-f0-9]{40}$' -or $Parent -ne $ExpectedParentHead) {
        throw 'Frontend commit ancestry verification failed.'
    }
    $Remaining = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
    if ($Remaining.Count -ne 0) { throw "Production tree changed during frontend save: $($Remaining -join ', ')" }
    $Tag = "prod-8093/20260814-frontend-sync-$($NewHead.Substring(0, 12))"
    & $GitExe -C $Root tag -a $Tag -m "Reviewed frontend production sync $ExecutionId"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to tag reviewed frontend update.' }

    $McpHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 30
    if (-not $McpHealth.ok) { throw 'MCP health failed after frontend Git save.' }
    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) { throw "Runtime PID changed during frontend Git save: $Port" }
    }
    $ManifestPath = "F:\BF_Git\V4_8093_PREVIEW.frontend.$ExecutionId.json"
    $Manifest = [ordered]@{
        schema = 'bf.8093-production-git-frontend-save.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        created_at = (Get-Date).ToString('o')
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        reviewed_path = $RelativePath
        sha256 = $ExpectedAssetSha256.ToUpperInvariant()
        sensitive_scan_completed = $true
        runtime_before = $Before
        runtime_after = $After
        service_restart_performed = $false
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 7), $Utf8NoBom)
    [ordered]@{
        ok = $true
        schema = 'bf.8093-production-git-frontend-save.v1'
        execution_id = $ExecutionId
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        sha256 = $ExpectedAssetSha256.ToUpperInvariant()
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
    } | ConvertTo-Json -Depth 7
} finally {
    if ($LockTaken -and $Mutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
