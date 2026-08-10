$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$logDir='F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取\logs'
$latest=Get-ChildItem -LiteralPath $logDir -Filter 'continuous_sync_pg_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if(-not$latest){throw 'realtime sync log is unavailable'}
Write-Host ("log="+$latest.FullName)
Get-Content -LiteralPath $latest.FullName -Tail 100 -Encoding UTF8
