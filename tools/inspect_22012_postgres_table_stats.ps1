$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
  Write-Host "PSQL_NOT_FOUND $psql"
  exit 0
}

$env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "User") }
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }
$pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
if (-not $pgUser) { $pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "User") }
if (-not $pgUser) { $pgUser = $env:GL02_PGUSER }
if (-not $pgUser) { $pgUser = "gl02_sync" }

$sql = @"
\pset pager off
SELECT current_database() AS database, pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT schemaname || '.' || relname AS table_name,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
       n_live_tup AS estimated_live_rows,
       n_dead_tup AS estimated_dead_rows,
       last_vacuum,
       last_autovacuum,
       last_analyze,
       last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname IN ('bf_sensor', 'bf_assistant')
ORDER BY pg_total_relation_size(relid) DESC;
SELECT 'one_minute_values' AS table_name, min(ts) AS min_ts, max(ts) AS max_ts, count(*) AS rows
FROM bf_sensor.one_minute_values;
SELECT 'raw_5s_values' AS table_name, min(ts) AS min_ts, max(ts) AS max_ts, count(*) AS rows
FROM bf_sensor.raw_5s_values;
"@

$tmp = Join-Path $env:TEMP ("bf_table_stats_{0}.sql" -f ([guid]::NewGuid().ToString("N")))
Set-Content -LiteralPath $tmp -Value $sql -Encoding UTF8
& $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=0 -f $tmp
Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
