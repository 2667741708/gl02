$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\foreman_points_coal_20260806'
$roots = @(
    (Join-Path $projectRoot '数据库同步和存取'),
    (Join-Path $projectRoot 'db_sync_storage')
)
$files = @(
    @{ Relative = 'run_realtime_sync_pg_bg.ps1'; Candidate = 'run_realtime_sync_pg_bg.ps1' },
    @{ Relative = 'config\sync_config.json'; Candidate = 'sync_config.json' },
    @{ Relative = 'config\点位清单.tsv'; Candidate = '点位清单.tsv' },
    @{ Relative = 'schema\postgresql_required_points.sql'; Candidate = 'postgresql_required_points.sql' },
    @{ Relative = 'src\sync_from_243_pg.py'; Candidate = 'sync_from_243_pg.py' },
    @{ Relative = 'src\coal_hourly.py'; Candidate = 'coal_hourly.py' },
    @{ Relative = 'src\init_foreman_points_pg_light.py'; Candidate = 'init_foreman_points_pg_light.py' }
)

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $projectRoot "logs\deploy_backups\foreman_points_files_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$results = @()
foreach ($root in $roots) {
    $rootName = if ($root -like '*db_sync_storage') { 'mirror' } else { 'main' }
    foreach ($item in $files) {
        $source = Join-Path $stage $item.Candidate
        $target = Join-Path $root $item.Relative
        if (-not (Test-Path -LiteralPath $source)) { throw "Missing candidate: $source" }
        if (Test-Path -LiteralPath $target) {
            $backupFile = Join-Path (Join-Path $backup $rootName) $item.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupFile) | Out-Null
            Copy-Item -LiteralPath $target -Destination $backupFile -Force
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        $temporary = "$target.foreman.new"
        Copy-Item -LiteralPath $source -Destination $temporary -Force
        Move-Item -LiteralPath $temporary -Destination $target -Force
        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($sourceHash -ne $targetHash) { throw "Hash mismatch: $target" }
        $results += [ordered]@{ root = $rootName; relative = $item.Relative; sha256 = $targetHash }
    }
}
[ordered]@{ installed = $true; backup = $backup; files = $results } | ConvertTo-Json -Depth 5
