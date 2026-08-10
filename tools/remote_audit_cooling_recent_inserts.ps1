$ErrorActionPreference = 'Stop'
function Read-Env([string]$name) {
  $value=[Environment]::GetEnvironmentVariable($name,'Machine')
  if(-not $value){$value=[Environment]::GetEnvironmentVariable($name,'User')}
  return $value
}
$env:PGHOST=Read-Env 'GL02_PGHOST'; $env:PGPORT=Read-Env 'GL02_PGPORT'; $env:PGDATABASE=Read-Env 'GL02_PGDATABASE'; $env:PGUSER=Read-Env 'GL02_PGUSER'; $env:PGPASSWORD=Read-Env 'GL02_PGPASSWORD'
$psql='F:\PostgreSQL\16\bin\psql.exe'
$sql=@'
WITH wanted(variable_name) AS (VALUES
 ('Q_soft_water'),('P_soft_water'),('Q_high_pressure_water'),('P_high_pressure_water'),('P_medium_pressure_water'),('ExpansionTankLevel')
), x AS (
 SELECT r.variable_name,v.ts,v.collected_at
 FROM wanted w JOIN bf_sensor.sensor_registry r USING(variable_name)
 JOIN bf_sensor.one_minute_values v USING(tag_long_name)
), summary AS (
 SELECT variable_name,
   count(*) FILTER(WHERE collected_at>=now()-interval '15 minutes') AS collected_last_15m,
   count(*) FILTER(WHERE collected_at>=now()-interval '15 minutes' AND ts<current_date-interval '1 day') AS old_ts_collected_last_15m,
   count(*) FILTER(WHERE collected_at>=now()-interval '2 hours') AS collected_last_2h,
   count(*) FILTER(WHERE collected_at>=now()-interval '2 hours' AND ts<current_date-interval '1 day') AS old_ts_collected_last_2h,
   min(ts) FILTER(WHERE collected_at>=now()-interval '2 hours') AS oldest_ts_collected_last_2h,
   max(collected_at) AS latest_collected_at
 FROM x GROUP BY variable_name
)
SELECT json_build_object(
 'checked_at',now(),
 'recent_collections',(SELECT json_agg(json_build_object(
   'variable_name',variable_name,
   'collected_last_15m',collected_last_15m,
   'old_ts_collected_last_15m',old_ts_collected_last_15m,
   'collected_last_2h',collected_last_2h,
   'old_ts_collected_last_2h',old_ts_collected_last_2h,
   'oldest_ts_collected_last_2h',oldest_ts_collected_last_2h,
   'latest_collected_at',latest_collected_at
 ) ORDER BY variable_name) FROM summary)
)::text;
'@
& $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if($LASTEXITCODE-ne 0){throw 'recent insert audit failed'}
