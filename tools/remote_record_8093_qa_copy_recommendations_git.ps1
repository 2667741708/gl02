[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$ExpectedParentHead,
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedSha256
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'REQ-QA-LOCAL-RECOMMENDATION-PRESERVATION-20260814'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$Relative = '高炉前端数据/frontend_dashboard_v3.server.html'
$Target = Join-Path $Root ($Relative -replace '/', '\')
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434, 8892)

function Get-ListenerPid([int]$Port) {
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Result = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Result[[string]$Port] = Get-ListenerPid $Port }
    return $Result
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
try {
    try { $Acquired = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $Acquired = $true }
    if (-not $Acquired) { throw 'Another 8093 deployment owns the mutex.' }
    if ((Get-Service -Name 'BFV4PreviewProxy8093').Status -ne 'Running') { throw '8093 service is not running.' }
    if (-not (Get-ListenerPid 8093)) { throw '8093 is not listening.' }
    $Before = Get-ProtectedMap
    foreach ($Key in $Before.Keys) { if (-not $Before[$Key]) { throw "Protected port $Key is not listening." } }
    $Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    if ($Head -ne $ExpectedParentHead) { throw "Unexpected production Git HEAD: $Head" }
    $ExpectedSha256 = $ExpectedSha256.ToUpperInvariant()
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $ExpectedSha256) {
        throw 'Deployed file hash drifted before Git save.'
    }
    $Text = Get-Content -LiteralPath $Target -Raw -Encoding UTF8
    foreach ($Pattern in @(
        '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
        '(?i)(postgres(?:ql)?|mysql|mssql)://[^:/\s]+:[^@/\s]+@'
    )) {
        if ($Text -match $Pattern) { throw 'Sensitive scan rejected the deployed HTML.' }
    }
    $Status = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
    if ($Status.Count -ne 1 -or ($Status[0].Substring(3) -replace '\\', '/') -ne $Relative) {
        throw "Exact deployed HTML status required: $($Status -join ', ')"
    }
    if ($Status[0].Substring(0, 1) -ne ' ') { throw 'Pre-existing staged production change blocks save.' }
    & $GitExe -C $Root add -- $Relative
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage deployed HTML.' }
    $Staged = @(& $GitExe -C $Root diff --cached --name-only 2>$null | Where-Object { $_ })
    if ($Staged.Count -ne 1 -or ($Staged[0] -replace '\\', '/') -ne $Relative) {
        throw 'Staged path is not the exact deployed HTML.'
    }
    & $GitExe -C $Root commit -m "feat: add QA copy and local recommendations [$RequirementId] [$ExecutionId]"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to commit deployed HTML.' }
    $NewHead = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
    $Parent = (& $GitExe -C $Root rev-parse "$NewHead^" 2>$null | Out-String).Trim()
    if ($Parent -ne $ExpectedParentHead) { throw 'Production commit ancestry verification failed.' }
    $Remaining = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
    if ($Remaining.Count) { throw "Production tree changed during Git save: $($Remaining -join ', ')" }
    $Tag = "prod-8093/20260814-qa-copy-recommendations-$($NewHead.Substring(0, 12))"
    & $GitExe -C $Root tag -a $Tag -m "QA copy and recommendations $ExecutionId"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create production version tag.' }
    $After = Get-ProtectedMap
    foreach ($Key in $Before.Keys) {
        if ($After[$Key] -ne $Before[$Key]) { throw "Protected PID changed during Git save: $Key" }
    }
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        parent_head = $ExpectedParentHead
        head = $NewHead
        tag = $Tag
        deployed_sha256 = $ExpectedSha256
        protected_before = $Before
        protected_after = $After
    } | ConvertTo-Json -Depth 6
} finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
