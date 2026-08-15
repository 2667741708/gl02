[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe',
    [string]$GitDir = 'F:\BF_Git\V4_8093_PREVIEW.git'
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

function Get-PortPid {
    param([int]$Port)
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAvailable = $false
try {
    try {
        $MutexAvailable = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $MutexAvailable = $true
    }
    if ($MutexAvailable) {
        $Mutex.ReleaseMutex()
    }
} finally {
    $Mutex.Dispose()
}

$Head = $null
$HeadExists = $false
$Tree = $null
$CommitSubject = $null
$CommitParents = $null
$HeadTags = @()
$StatusCount = $null
$StagedCount = $null
$StatusRows = @()
if ((Test-Path -LiteralPath $GitExe -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $Root '.git'))) {
    $HeadOutput = & $GitExe -C $Root rev-parse --verify HEAD 2>$null
    $HeadExists = $LASTEXITCODE -eq 0
    if ($HeadExists) {
        $Head = ($HeadOutput | Out-String).Trim()
        $Tree = (& $GitExe -C $Root rev-parse 'HEAD^{tree}' 2>$null | Out-String).Trim()
        $CommitSubject = (& $GitExe -C $Root log -1 --format=%s 2>$null | Out-String).Trim()
        $CommitParents = (& $GitExe -C $Root log -1 --format=%P 2>$null | Out-String).Trim()
        $HeadTags = @(& $GitExe -C $Root tag --points-at HEAD 2>$null | Where-Object { $_ })
    }
    $Status = @(& $GitExe -C $Root status --porcelain --untracked-files=no 2>$null)
    $StatusCount = $Status.Count
    $StatusRows = @($Status | ForEach-Object {
        [ordered]@{ state = $_.Substring(0, 2); path = $_.Substring(3) }
    })
    $Staged = @(& $GitExe -C $Root diff --cached --name-only 2>$null)
    $StagedCount = @($Staged | Where-Object { $_ }).Count
}

$Processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match '(?i)(initialize-baseline|remote_initialize_8093_git_baseline|PortableGit\\.*git\.exe)'
} | ForEach-Object {
    [ordered]@{ process_id = [int]$_.ProcessId; name = [string]$_.Name }
})
$Manifests = @(Get-ChildItem -LiteralPath 'F:\BF_Git' -Filter 'V4_8093_PREVIEW.baseline.*.json' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 3 |
    ForEach-Object { [ordered]@{ path = $_.FullName; length = [long]$_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash } })
$Runtime = [ordered]@{}
foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
    $Runtime[[string]$Port] = Get-PortPid -Port $Port
}

[ordered]@{
    schema = 'bf.8093-git-baseline-state-probe.v1'
    root_git_pointer_exists = Test-Path -LiteralPath (Join-Path $Root '.git')
    git_dir_exists = Test-Path -LiteralPath $GitDir
    head_exists = $HeadExists
    head = $Head
    tree = $Tree
    commit_subject = $CommitSubject
    commit_parents = $CommitParents
    head_tags = $HeadTags
    tracked_status_count = $StatusCount
    tracked_status = $StatusRows
    staged_count = $StagedCount
    mutex_available = $MutexAvailable
    matching_processes = $Processes
    manifests = $Manifests
    runtime = $Runtime
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
