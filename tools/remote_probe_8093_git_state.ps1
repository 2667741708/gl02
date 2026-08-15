$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$dotGit = Join-Path $root '.git'
$gitCandidates = @(
    (Get-Command git.exe -ErrorAction SilentlyContinue).Source,
    'F:\Tools\PortableGit\cmd\git.exe',
    'C:\Program Files\Git\cmd\git.exe',
    'C:\Program Files\Git\bin\git.exe',
    'C:\Program Files (x86)\Git\cmd\git.exe',
    'C:\Users\Administrator\AppData\Local\Programs\Git\cmd\git.exe'
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -Unique
$git = $gitCandidates | Select-Object -First 1
$dotGitContent = if (Test-Path -LiteralPath $dotGit -PathType Leaf) {
    (Get-Content -LiteralPath $dotGit -Raw -Encoding UTF8).Trim()
} else { '' }
if (-not $git) {
    [ordered]@{
        schema = 'ops.8093.git-state.v1'
        root = $root
        git_executable = $null
        git_available = $false
        dot_git_exists = Test-Path -LiteralPath $dotGit
        dot_git_type = if (Test-Path -LiteralPath $dotGit -PathType Container) { 'directory' } elseif (Test-Path -LiteralPath $dotGit -PathType Leaf) { 'file' } else { 'missing' }
        dot_git_file_content = $dotGitContent
        searched_git_paths = @(
            'PATH',
            'F:\Tools\PortableGit\cmd\git.exe',
            'C:\Program Files\Git\cmd\git.exe',
            'C:\Program Files\Git\bin\git.exe',
            'C:\Program Files (x86)\Git\cmd\git.exe',
            'C:\Users\Administrator\AppData\Local\Programs\Git\cmd\git.exe'
        )
    } | ConvertTo-Json -Depth 6
    exit 0
}
$inside = (& $git -C $root rev-parse --is-inside-work-tree 2>$null | Out-String).Trim()
$top = (& $git -C $root rev-parse --show-toplevel 2>$null | Out-String).Trim()
$common = (& $git -C $root rev-parse --git-common-dir 2>$null | Out-String).Trim()
$gitDir = (& $git -C $root rev-parse --git-dir 2>$null | Out-String).Trim()
$head = (& $git -C $root rev-parse HEAD 2>$null | Out-String).Trim()
$branch = (& $git -C $root branch --show-current 2>$null | Out-String).Trim()
$status = @(& $git -C $root status --short --untracked-files=no 2>$null)
$remotes = @(& $git -C $root remote -v 2>$null)
$worktrees = @(& $git -C $root worktree list --porcelain 2>$null)

[ordered]@{
    schema = 'ops.8093.git-state.v1'
    root = $root
    git_executable = $git
    git_available = $true
    dot_git_exists = Test-Path -LiteralPath $dotGit
    dot_git_type = if (Test-Path -LiteralPath $dotGit -PathType Container) { 'directory' } elseif (Test-Path -LiteralPath $dotGit -PathType Leaf) { 'file' } else { 'missing' }
    dot_git_file_content = $dotGitContent
    inside_work_tree = $inside
    top_level = $top
    git_dir = $gitDir
    git_common_dir = $common
    head = $head
    branch = $branch
    tracked_change_count = $status.Count
    tracked_changes = $status
    remotes = $remotes
    worktrees = $worktrees
} | ConvertTo-Json -Depth 6
