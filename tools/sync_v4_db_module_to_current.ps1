[CmdletBinding()]
param(
    [string]$SourceRoot = 'D:\文件\服务器实际运行版V4\数据库同步和存取',
    [string]$TargetRoot = '',
    [switch]$WhatIfMode
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $TargetRoot) {
    $TargetRoot = Join-Path $projectRoot '数据库同步和存取'
}
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$target = [System.IO.Path]::GetFullPath($TargetRoot)
if (-not $source.EndsWith('数据库同步和存取')) {
    throw "Unexpected source module root: $source"
}
if (-not $target.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Target must remain inside the current project: $target"
}

$topLevelFiles = @(
    'create_sync_tasks_22012.ps1',
    'IMES只读采集说明.md',
    'IMES数据存储位置与时间范围.md',
    'install_postgresql_22012.ps1',
    'install_postgresql_portable_22012.ps1',
    'install_sync_watchdog_task.ps1',
    'PostgreSQL自动值守配置.md',
    'README.md',
    'run_22012_continuous_sync.ps1',
    'run_22012_history_sync_90d.ps1',
    'run_22012_init.ps1',
    'run_22012_从IMES数据库同步.ps1',
    'run_history_sync_pg_bg.ps1',
    'run_raw_5s_sync_pg_once.ps1',
    'run_realtime_sync_pg_bg.ps1',
    'run_sync_watchdog.ps1',
    'setup_external_readonly_access.ps1',
    'start_sync_jobs_22012.ps1',
    '从IMES数据库同步.py',
    '同步守护任务说明.md',
    '明确指令.md'
)
$directoryRules = [ordered]@{
    config = @('.json', '.tsv')
    schema = @('.sql')
    src = @('.py')
}

$configPath = Join-Path $source 'config\sync_config.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($config.database.postgresql.password) {
    throw 'Refusing to copy sync_config.json because it contains a plaintext password.'
}

$files = [System.Collections.Generic.List[System.IO.FileInfo]]::new()
foreach ($name in $topLevelFiles) {
    $path = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required source file is missing: $path"
    }
    $files.Add((Get-Item -LiteralPath $path))
}
foreach ($entry in $directoryRules.GetEnumerator()) {
    $directory = Join-Path $source $entry.Key
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw "Required source directory is missing: $directory"
    }
    Get-ChildItem -LiteralPath $directory -File | Where-Object {
        $_.Extension -in $entry.Value
    } | ForEach-Object { $files.Add($_) }
}

$manifestFiles = @()
foreach ($file in $files | Sort-Object FullName -Unique) {
    $relative = $file.FullName.Substring($source.Length).TrimStart('\')
    $destination = Join-Path $target $relative
    $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    if (-not $WhatIfMode) {
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
        $targetHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($targetHash -ne $sourceHash) {
            throw "Hash mismatch after copy: $relative"
        }
    }
    $manifestFiles += [ordered]@{
        path = $relative.Replace('\', '/')
        bytes = $file.Length
        sha256 = $sourceHash
    }
}

$manifest = [ordered]@{
    schema = 'bf.db-sync-module-manifest.v1'
    generated_at = (Get-Date).ToString('o')
    source_root = $source
    target_root = $target
    what_if = [bool]$WhatIfMode
    exclusions = @('backups', 'logs', 'data', 'imes_exports', '__pycache__', '*.pyc', '*.env', 'tmp_*')
    file_count = $manifestFiles.Count
    files = $manifestFiles
}
if (-not $WhatIfMode) {
    $manifestPath = Join-Path $target 'module_sync_manifest.json'
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}
$manifest | ConvertTo-Json -Depth 6
