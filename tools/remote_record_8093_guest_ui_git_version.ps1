[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedParentHead,
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedPageSha256
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-8093-GUEST-UI-RECOVERY-20260814'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$RelativePath = '高炉前端数据/frontend_dashboard_v3.server.html'
$FullPath = Join-Path $Root ($RelativePath -replace '/', '\')
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434, 8892)
$Mutex = $null
$LockTaken = $false

function Get-PortPid([int]$Port) {
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

function Get-RuntimeSnapshot {
    $Rows = [ordered]@{ '8093' = Get-PortPid 8093 }
    foreach ($Port in $ProtectedPorts) { $Rows[[string]$Port] = Get-PortPid $Port }
    return $Rows
}

try {
    if ((Get-Service -Name 'BFV4PreviewProxy8093').Status -ne 'Running') { throw '8093 service is not running.' }
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093) + $ProtectedPorts) {
        if (-not $Before[[string]$Port]) { throw "Required listener missing: $Port" }
    }
    $Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    if ($Head -ne $ExpectedParentHead) { throw "Unexpected production Git HEAD: $Head" }
    $ExpectedHash = $ExpectedPageSha256.ToUpperInvariant()
    if ((Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash -ne $ExpectedHash) {
        throw 'Accepted dashboard hash drifted before Git save.'
    }
    $Text = Get-Content -LiteralPath $FullPath -Raw -Encoding utf8
    foreach ($Marker in @('function QaGuestNav', '登录私有会话（可选）', '继续匿名使用')) {
        if (-not $Text.Contains($Marker)) { throw "Accepted marker missing before Git save: $Marker" }
    }
    foreach ($Pattern in @(
        '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
        '(?i)(password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*["''][^"'']{4,}["'']',
        '(?i)(postgres(?:ql)?|mysql|mssql)://[^:/\s]+:[^@/\s]+@'
    )) {
        if ($Text -match $Pattern) { throw 'Sensitive scan rejected the dashboard.' }
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try { $LockTaken = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $LockTaken = $true }
    if (-not $LockTaken) { throw 'Production maintenance mutex is busy.' }
    $PreStaged = @(& $GitExe -C $Root diff --cached --name-only 2>$null | Where-Object { $_ })
    if ($PreStaged.Count -ne 0) { throw "Pre-existing staged changes block Git save: $($PreStaged -join ', ')" }
    & $GitExe -C $Root diff --quiet -- $RelativePath
    if ($LASTEXITCODE -eq 0) { throw 'Dashboard has no production change to commit.' }

    & $GitExe -C $Root add -- $RelativePath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the accepted dashboard.' }
    $Staged = @(& $GitExe -C $Root diff --cached --name-only 2>$null | Where-Object { $_ })
    if ($Staged.Count -ne 1 -or ($Staged[0] -replace '\\', '/') -ne $RelativePath) {
        throw "Unexpected staged path set: $($Staged -join ', ')"
    }
    & $GitExe -C $Root diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'Staged dashboard failed git diff --check.' }
    $Subject = "fix: restore anonymous 8093 assistant UI [$RequirementId] [$ExecutionId]"
    & $GitExe -C $Root commit -m $Subject
    if ($LASTEXITCODE -ne 0) { throw 'Failed to commit accepted dashboard.' }
    $NewHead = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    $Parent = (& $GitExe -C $Root rev-parse "$NewHead^" 2>$null | Out-String).Trim()
    if ($Parent -ne $ExpectedParentHead) { throw 'Production commit ancestry verification failed.' }
    $Committed = @(& $GitExe -C $Root diff-tree --no-commit-id --name-only -r $NewHead 2>$null | Where-Object { $_ })
    if ($Committed.Count -ne 1 -or ($Committed[0] -replace '\\', '/') -ne $RelativePath) {
        throw "Unexpected committed path set: $($Committed -join ', ')"
    }
    $Tag = "prod-8093/20260814-guest-ui-$($NewHead.Substring(0, 12))"
    & $GitExe -C $Root tag -a $Tag -m "8093 anonymous guest UI recovery $ExecutionId"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to tag accepted dashboard.' }

    $Bootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 30
    if (-not $Bootstrap.ok -or $Bootstrap.access_mode -ne 'guest_shared') { throw 'Guest bootstrap failed after Git save.' }
    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093) + $ProtectedPorts) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) { throw "Runtime PID changed during Git save: $Port" }
    }
    $ManifestPath = "F:\BF_Git\V4_8093_PREVIEW.guest-ui.$ExecutionId.json"
    $Manifest = [ordered]@{
        schema = 'bf.8093-production-git-guest-ui-save.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        created_at = (Get-Date).ToString('o')
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        reviewed_path = $RelativePath
        sha256 = $ExpectedHash
        runtime_before = $Before
        runtime_after = $After
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 7), $Utf8NoBom)
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        reviewed_path = $RelativePath
        sha256 = $ExpectedHash
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
    } | ConvertTo-Json -Depth 7
} finally {
    if ($LockTaken -and $Mutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
