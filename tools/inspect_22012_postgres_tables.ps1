$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

Write-Host "===== PSQL_PATHS ====="
$psql = $null
foreach ($candidate in @(
  "F:\PostgreSQL\16\bin\psql.exe",
  "F:\PostgreSQL\15\bin\psql.exe",
  "C:\Program Files\PostgreSQL\16\bin\psql.exe",
  "C:\Program Files\PostgreSQL\15\bin\psql.exe"
)) {
  $exists = Test-Path -LiteralPath $candidate
  [PSCustomObject]@{ Path = $candidate; Exists = $exists } | Format-List
  if ($exists -and -not $psql) { $psql = $candidate }
}

Write-Host "===== PYTHON_DB_DRIVERS ====="
python -c "import importlib.util; print('psycopg', importlib.util.find_spec('psycopg') is not None); print('psycopg2', importlib.util.find_spec('psycopg2') is not None)"

Write-Host "===== DB_QUERY ====="
if (-not $psql) {
  Write-Host "NO_PSQL_AVAILABLE"
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
SELECT max(ts) AS one_minute_max_ts,
       localtimestamp AS db_now,
       round(extract(epoch from (localtimestamp - max(ts)))::numeric / 60, 3) AS lag_min,
       count(DISTINCT tag_long_name) FILTER (WHERE ts >= (SELECT max(ts)-interval '10 minutes' FROM bf_sensor.one_minute_values)) AS tags_latest_10m
FROM bf_sensor.one_minute_values;
SELECT 'bf_sensor.one_minute_values' AS table_name, pg_size_pretty(pg_total_relation_size('bf_sensor.one_minute_values')) AS total_size, count(*) AS rows FROM bf_sensor.one_minute_values
UNION ALL SELECT 'bf_sensor.raw_5s_values', pg_size_pretty(pg_total_relation_size('bf_sensor.raw_5s_values')), count(*) FROM bf_sensor.raw_5s_values
UNION ALL SELECT 'bf_sensor.daily_baselines', pg_size_pretty(pg_total_relation_size('bf_sensor.daily_baselines')), count(*) FROM bf_sensor.daily_baselines
UNION ALL SELECT 'bf_sensor.diagnosis_snapshots', pg_size_pretty(pg_total_relation_size('bf_sensor.diagnosis_snapshots')), count(*) FROM bf_sensor.diagnosis_snapshots
UNION ALL SELECT 'bf_sensor.data_quality_checks', pg_size_pretty(pg_total_relation_size('bf_sensor.data_quality_checks')), count(*) FROM bf_sensor.data_quality_checks
UNION ALL SELECT 'bf_sensor.automation_runs', pg_size_pretty(pg_total_relation_size('bf_sensor.automation_runs')), count(*) FROM bf_sensor.automation_runs
UNION ALL SELECT 'bf_sensor.diagnosis_queue', pg_size_pretty(pg_total_relation_size('bf_sensor.diagnosis_queue')), count(*) FROM bf_sensor.diagnosis_queue
UNION ALL SELECT 'bf_sensor.short_window_summaries', pg_size_pretty(pg_total_relation_size('bf_sensor.short_window_summaries')), count(*) FROM bf_sensor.short_window_summaries
UNION ALL SELECT 'bf_sensor.zero_value_audits', pg_size_pretty(pg_total_relation_size('bf_sensor.zero_value_audits')), count(*) FROM bf_sensor.zero_value_audits
ORDER BY rows DESC;
"@

$tmp = Join-Path $env:TEMP ("bf_runtime_db_{0}.sql" -f ([guid]::NewGuid().ToString("N")))
Set-Content -LiteralPath $tmp -Value $sql -Encoding UTF8
& $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=0 -f $tmp
Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
