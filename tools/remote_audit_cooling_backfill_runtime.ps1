$ErrorActionPreference='Stop'
function Read-Env([string]$name){$v=[Environment]::GetEnvironmentVariable($name,'Machine');if(-not $v){$v=[Environment]::GetEnvironmentVariable($name,'User')};return $v}
$env:PGHOST=Read-Env 'GL02_PGHOST';$env:PGPORT=Read-Env 'GL02_PGPORT';$env:PGDATABASE=Read-Env 'GL02_PGDATABASE';$env:PGUSER=Read-Env 'GL02_PGUSER';$env:PGPASSWORD=Read-Env 'GL02_PGPASSWORD'
$psql='F:\PostgreSQL\16\bin\psql.exe'
$sql=@'
WITH wanted(variable_name) AS (VALUES ('Q_soft_water'),('P_soft_water'),('Q_high_pressure_water'),('P_high_pressure_water'),('P_medium_pressure_water'),('ExpansionTankLevel')),
x AS (
 SELECT r.variable_name,v.ts,v.collected_at FROM wanted w JOIN bf_sensor.sensor_registry r USING(variable_name) JOIN bf_sensor.one_minute_values v USING(tag_long_name)
), summary AS (
 SELECT variable_name,count(*) AS total_rows,
  count(*) FILTER(WHERE collected_at>=now()-interval '5 minutes') AS rows_collected_last_5m,
  count(*) FILTER(WHERE collected_at>=now()-interval '5 minutes' AND ts<current_date-interval '1 day') AS historical_rows_last_5m,
  min(ts) FILTER(WHERE collected_at>=now()-interval '5 minutes' AND ts<current_date-interval '1 day') AS historical_min_ts_last_5m,
  max(ts) FILTER(WHERE collected_at>=now()-interval '5 minutes' AND ts<current_date-interval '1 day') AS historical_max_ts_last_5m,
  max(ts) FILTER(WHERE ts<current_date-interval '1 day') AS max_historical_ts_present
 FROM x GROUP BY variable_name
)
SELECT json_build_object(
 'checked_at',now(),
 'progress',(SELECT json_agg(json_build_object(
  'variable_name',variable_name,'total_rows',total_rows,'rows_collected_last_5m',rows_collected_last_5m,
  'historical_rows_last_5m',historical_rows_last_5m,'historical_min_ts_last_5m',historical_min_ts_last_5m,
  'historical_max_ts_last_5m',historical_max_ts_last_5m,'max_historical_ts_present',max_historical_ts_present
 ) ORDER BY variable_name) FROM summary),
 'active_database_sessions',(SELECT json_agg(json_build_object('pid',pid,'state',state,'query_start',query_start,'wait_event_type',wait_event_type,'wait_event',wait_event,'query',left(query,500))) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state<>'idle')
)::text;
'@
$db=& $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if($LASTEXITCODE-ne 0){throw 'runtime SQL failed'}
$cutoff=(Get-Date).AddHours(-2)
$procs=Get-CimInstance Win32_Process | Where-Object {$_.CreationDate -ge $cutoff -and ($_.Name -match 'python|powershell')} | Select-Object ProcessId,ParentProcessId,CreationDate,Name,CommandLine
[pscustomobject]@{database=($db|ConvertFrom-Json);recent_processes=@($procs)}|ConvertTo-Json -Depth 8
