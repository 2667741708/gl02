$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$logDir = 'F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\logs'
$latest = Get-ChildItem -LiteralPath $logDir -Filter 'continuous_sync_pg_*.log' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $latest) { throw 'No continuous sync log found' }
Write-Output "LOG=$($latest.FullName)"
Write-Output "LAST_WRITE=$($latest.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
Get-Content -LiteralPath $latest.FullName -Encoding UTF8 -Tail 40 |
    ForEach-Object { Write-Output ([string]$_) }
