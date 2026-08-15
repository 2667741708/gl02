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

try {
    $Before = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if (-not $Before[[string]$Port]) { throw "Required listener missing: $Port" }
    }
    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) { throw 'Production maintenance mutex is busy.' }

    $Head = (& $GitExe -C $Root rev-parse --verify HEAD 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $Head -notmatch '^[a-f0-9]{40}$') { throw 'Valid baseline HEAD is missing.' }
    $Tree = (& $GitExe -C $Root rev-parse 'HEAD^{tree}' 2>$null | Out-String).Trim()
    $Parents = (& $GitExe -C $Root log -1 --format=%P 2>$null | Out-String).Trim()
    if ($Parents) { throw 'Baseline HEAD is not an initial root commit.' }
    $Subject = (& $GitExe -C $Root log -1 --format=%s 2>$null | Out-String).Trim()
    if (-not $Subject.Contains("[$RequirementId]")) { throw "Unexpected baseline commit subject: $Subject" }
    $TrackedPaths = @(& $GitExe -C $Root ls-tree -r --name-only HEAD 2>$null | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $TrackedPaths.Count -lt 10) { throw 'Baseline tree is incomplete.' }
    foreach ($RequiredPath in $RequiredTrackedPaths) {
        if ($TrackedPaths -notcontains $RequiredPath) { throw "Baseline tree is missing required target: $RequiredPath" }
    }

    $Tag = "prod-8093/20260814-initial-$($Head.Substring(0, 12))"
    $ExistingTags = @(& $GitExe -C $Root tag --points-at HEAD 2>$null | Where-Object { $_ })
    if ($ExistingTags -notcontains $Tag) {
        & $GitExe -C $Root tag -a $Tag -m "Reviewed 220.12 production baseline $ExecutionId" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create initial production baseline tag.' }
    }
    $Status = @(& $GitExe -C $Root status --porcelain --untracked-files=no 2>$null | Where-Object { $_ })
    $StatusRows = @($Status | ForEach-Object { [ordered]@{ state = $_.Substring(0, 2); path = $_.Substring(3) } })
    $GitVersion = (& $GitExe --version 2>&1 | Out-String).Trim()
    $ManifestPath = "F:\BF_Git\V4_8093_PREVIEW.baseline.$ExecutionId.json"
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
        commit_subject = $Subject
        git_version = $GitVersion
        tracked_count = $TrackedPaths.Count
        staged_sensitive_scan_completed = $true
        finalized_after_transport_timeout = $true
        sensitive_values_recorded = $false
        working_tree_changes_after_baseline = $StatusRows
    }
    [IO.File]::WriteAllText($ManifestPath, ($Manifest | ConvertTo-Json -Depth 6), $Utf8NoBom)

    $After = Get-RuntimeSnapshot
    foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
        if ($Before[[string]$Port] -ne $After[[string]$Port]) {
            throw "Runtime PID changed while finalizing baseline metadata: port=$Port"
        }
    }
    [ordered]@{
        ok = $true
        schema = 'bf.8093-production-git-baseline-finalize.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        head = $Head
        tree = $Tree
        tag = $Tag
        tracked_count = $TrackedPaths.Count
        working_tree_changes_after_baseline = $StatusRows
        manifest_path = $ManifestPath
        runtime_before = $Before
        runtime_after = $After
        service_restart_performed = $false
    } | ConvertTo-Json -Depth 7
} finally {
    if ($LockTaken -and $Mutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
