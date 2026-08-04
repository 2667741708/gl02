$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, "User") }
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

$psql = @("F:\PostgreSQL\16\bin\psql.exe", "C:\Program Files\PostgreSQL\16\bin\psql.exe", "psql.exe") |
    Where-Object { $_ -eq "psql.exe" -or (Test-Path -LiteralPath $_) } |
    Select-Object -First 1

$sql = @"
WITH latest_sensor AS (
  SELECT max(ts) AS max_ts FROM bf_sensor.one_minute_values
),
latest_diag AS (
  SELECT * FROM bf_sensor.diagnosis_snapshots ORDER BY diagnosis_ts DESC, updated_at DESC LIMIT 1
),
latest_queue AS (
  SELECT * FROM bf_sensor.diagnosis_queues ORDER BY queue_end_ts DESC, updated_at DESC LIMIT 1
),
latest_summary AS (
  SELECT * FROM bf_sensor.short_window_summaries ORDER BY created_at DESC LIMIT 1
),
latest_run AS (
  SELECT * FROM bf_sensor.automation_runs ORDER BY started_at DESC LIMIT 1
)
SELECT json_build_object(
  'db_now', localtimestamp::text,
  'sensor_max_ts', (SELECT max_ts::text FROM latest_sensor),
  'sensor_lag_min', (SELECT round(extract(epoch from (localtimestamp - max_ts))::numeric/60, 3) FROM latest_sensor),
  'tags_latest_10m', (
    SELECT count(DISTINCT tag_long_name)
    FROM bf_sensor.one_minute_values
    WHERE ts >= (SELECT max_ts - interval '10 minutes' FROM latest_sensor)
  ),
  'diagnosis_ts', (SELECT diagnosis_ts::text FROM latest_diag),
  'diagnosis_lag_from_sensor_min', (SELECT round(extract(epoch from ((SELECT max_ts FROM latest_sensor) - diagnosis_ts))::numeric/60, 3) FROM latest_diag),
  'main_label', (SELECT main_label FROM latest_diag),
  'main_score', (SELECT main_score FROM latest_diag),
  'queue_id', (SELECT queue_id FROM latest_queue),
  'queue_end_ts', (SELECT queue_end_ts::text FROM latest_queue),
  'queue_count', (SELECT diagnosis_count FROM latest_queue),
  'queue_expected', (SELECT expected_count FROM latest_queue),
  'queue_status', (SELECT status FROM latest_queue),
  'summary_id', (SELECT summary_id FROM latest_summary),
  'summary_queue_id', (SELECT queue_id FROM latest_summary),
  'summary_created_at', (SELECT created_at::text FROM latest_summary),
  'summary_status', (SELECT status FROM latest_summary),
  'summary_chars', (SELECT length(llm_summary) FROM latest_summary),
  'summary_matches_latest_queue', (SELECT queue_id FROM latest_summary) = (SELECT queue_id FROM latest_queue),
  'last_run_task', (SELECT task_name FROM latest_run),
  'last_run_status', (SELECT status FROM latest_run),
  'last_run_window_end', (SELECT window_end::text FROM latest_run),
  'last_run_finished_at', (SELECT finished_at::text FROM latest_run)
)::text;
"@

& $psql -w -h $env:GL02_PGHOST -p $env:GL02_PGPORT -U $env:GL02_PGUSER -d $env:GL02_PGDATABASE -tA -c $sql
