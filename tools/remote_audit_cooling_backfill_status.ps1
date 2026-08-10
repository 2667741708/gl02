$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
function Read-Env([string]$name) {
  $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
  if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, 'User') }
  return $value
}
$env:PGHOST = Read-Env 'GL02_PGHOST'
$env:PGPORT = Read-Env 'GL02_PGPORT'
$env:PGDATABASE = Read-Env 'GL02_PGDATABASE'
$env:PGUSER = Read-Env 'GL02_PGUSER'
$env:PGPASSWORD = Read-Env 'GL02_PGPASSWORD'
$psql = 'F:\PostgreSQL\16\bin\psql.exe'
$sql = @'
WITH wanted(variable_name) AS (VALUES
 ('Q_soft_water'),('P_soft_water'),('Q_high_pressure_water'),
 ('P_high_pressure_water'),('P_medium_pressure_water'),('ExpansionTankLevel')
), tags AS (
 SELECT r.variable_name,r.tag_long_name FROM bf_sensor.sensor_registry r JOIN wanted w USING(variable_name)
), daily AS (
 SELECT t.variable_name,v.ts::date AS day,count(*) AS rows,
        count(*) FILTER (WHERE v.value IS NOT NULL) AS numeric_rows,
        min(v.ts) AS first_ts,max(v.ts) AS last_ts
 FROM tags t LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name=t.tag_long_name
 WHERE v.ts >= current_date-interval '35 days'
 GROUP BY t.variable_name,v.ts::date
), totals AS (
 SELECT t.variable_name,count(v.*) FILTER (WHERE v.ts>=current_date-interval '30 days') AS rows_30d,
        min(v.ts) AS first_available_ts,max(v.ts) AS latest_ts
 FROM tags t LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name=t.tag_long_name
 GROUP BY t.variable_name
), base AS (
 SELECT DISTINCT ON (b.variable_name) b.variable_name,b.baseline_day,b.baseline_days,b.sample_count,
        b.coverage_ratio,b.median_ref,b.iqr_ref,b.p25,b.p75,b.baseline_window_start,
        b.baseline_window_end,b.updated_at
 FROM bf_sensor.daily_baselines b JOIN wanted w USING(variable_name)
 WHERE b.baseline_days=30
 ORDER BY b.variable_name,b.baseline_day DESC,b.updated_at DESC
)
SELECT json_build_object(
 'checked_at',now(),
 'columns',(SELECT json_agg(column_name ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='bf_sensor' AND table_name='one_minute_values'),
 'variables',(SELECT json_agg(json_build_object(
   'variable_name',w.variable_name,'rows_30d',coalesce(t.rows_30d,0),'first_available_ts',t.first_available_ts,'latest_ts',t.latest_ts,
   'baseline',json_build_object('baseline_day',b.baseline_day,'baseline_days',b.baseline_days,'sample_count',b.sample_count,
      'coverage_ratio',b.coverage_ratio,'median_ref',b.median_ref,'iqr_ref',b.iqr_ref,'p25',b.p25,'p75',b.p75,
      'window_start',b.baseline_window_start,'window_end',b.baseline_window_end,'updated_at',b.updated_at),
   'daily',(SELECT json_agg(json_build_object('day',d.day,'rows',d.rows,'numeric_rows',d.numeric_rows,'first_ts',d.first_ts,'last_ts',d.last_ts) ORDER BY d.day) FROM daily d WHERE d.variable_name=w.variable_name)
 ) ORDER BY w.variable_name) FROM wanted w LEFT JOIN totals t USING(variable_name) LEFT JOIN base b USING(variable_name))
)::text;
'@
$dbJson = & $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if ($LASTEXITCODE -ne 0) { throw 'database audit failed' }
$tasks = Get-ScheduledTask | Where-Object {
  $_.TaskName -match 'baseline|pspace|backfill|cooling' -or $_.Actions.Arguments -match 'baseline|pspace|backfill|cooling'
} | ForEach-Object {
  $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath
  [pscustomobject]@{path=($_.TaskPath+$_.TaskName);state=$_.State.ToString();last_run=$info.LastRunTime;last_result=$info.LastTaskResult;next_run=$info.NextRunTime;execute=$_.Actions.Execute;arguments=$_.Actions.Arguments}
}
$processes = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'baseline_maintainer|pspace|backfill|cooling' } | Select-Object ProcessId,ParentProcessId,CreationDate,Name,CommandLine
[pscustomobject]@{database=($dbJson|ConvertFrom-Json);tasks=@($tasks);processes=@($processes)} | ConvertTo-Json -Depth 12
