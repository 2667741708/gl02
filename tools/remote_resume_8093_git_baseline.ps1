[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe',
    [string]$GitDir = 'F:\BF_Git\V4_8093_PREVIEW.git',
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
$Mutex = $null
$LockTaken = $false
$RequiredTrackedPaths = @(
    '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
    '高炉前端数据/智能助手/backend/mcp_host/client_manager.py',
    '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py'
)

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

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $Output = & $GitExe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($Output | Out-String)"
    }
    return ($Output | Out-String).Trim()
}

try {
    if (-not (Test-Path -LiteralPath (Join-Path $Root '.git'))) {
        throw 'Production Git pointer is missing.'
    }
    if (-not (Test-Path -LiteralPath $GitDir -PathType Container)) {
        throw 'Separate production Git directory is missing.'
    }
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if (-not $Before[[string]$Port]) { throw "Required listener missing before baseline resume: $Port" }
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) {
        throw 'Another 8093 deployment or production maintenance operation owns the global mutex.'
    }

    & $GitExe -C $Root rev-parse --verify HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        throw 'HEAD already exists; baseline resume refuses to create a second initial commit.'
    }
    $StagedPaths = @(& $GitExe -C $Root diff --cached --name-only 2>$null | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $StagedPaths.Count -lt 10) {
        throw "Staged sensitive-scan result is missing or too small: $($StagedPaths.Count)"
    }
    foreach ($RequiredPath in $RequiredTrackedPaths) {
        if ($StagedPaths -notcontains $RequiredPath) {
            throw "Required 8093 deployment target is not staged: $RequiredPath"
        }
    }
    foreach ($RequiredPath in $RequiredTrackedPaths) {
        $WorkingObject = Invoke-Git -Arguments @('-C', $Root, 'hash-object', '--', $RequiredPath)
        $IndexRow = Invoke-Git -Arguments @('-C', $Root, 'ls-files', '-s', '--', $RequiredPath)
        $IndexObject = ($IndexRow -split '\s+')[1]
        if ($WorkingObject -ne $IndexObject) {
            throw "Required target changed after sensitive scan: $RequiredPath"
        }
    }

    $GitVersion = (& $GitExe --version 2>&1 | Out-String).Trim()
    $CommitMessage = "baseline: reviewed 220.12 production source [$RequirementId] [$ExecutionId]"
    Invoke-Git -Arguments @('-C', $Root, 'commit', '-m', $CommitMessage) | Out-Null
    $Head = Invoke-Git -Arguments @('-C', $Root, 'rev-parse', 'HEAD')
    $Tree = Invoke-Git -Arguments @('-C', $Root, 'rev-parse', 'HEAD^{tree}')
    $Tag = "prod-8093/20260814-initial-$($Head.Substring(0, 12))"
    Invoke-Git -Arguments @('-C', $Root, 'tag', '-a', $Tag, '-m', "Reviewed 220.12 production baseline $ExecutionId") | Out-Null

    $GitParent = Split-Path -Parent $GitDir
    $ManifestPath = Join-Path $GitParent "V4_8093_PREVIEW.baseline.$ExecutionId.json"
    $Manifest = [ordered]@{
        schema = 'bf.8093-production-git-baseline-manifest.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        created_at = (Get-Date).ToString('o')
        root = $Root
        git_dir = $GitDir
        head = $Head
        tree = $Tree
        tag = $Tag
        git_version = $GitVersion
        tracked_count = $StagedPaths.Count
        staged_sensitive_scan_completed = $true
        resumed_after_transport_timeout = $true
        sensitive_values_recorded = $false
        required_targets = $RequiredTrackedPaths
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 6), $Utf8NoBom)

    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) {
            throw "Runtime PID changed while finalizing Git baseline: port=$Port before=$($Before[[string]$Port]) after=$($After[[string]$Port])"
        }
    }
    [ordered]@{
        ok = $true
        schema = 'bf.8093-production-git-baseline.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        git_version = $GitVersion
        root = $Root
        git_dir = $GitDir
        head = $Head
        tree = $Tree
        tag = $Tag
        tracked_count = $StagedPaths.Count
        staged_sensitive_scan_completed = $true
        resumed_after_transport_timeout = $true
        sensitive_values_recorded = $false
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
        service_restart_performed = $false
    } | ConvertTo-Json -Depth 7
} finally {
    if ($LockTaken -and $Mutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
