$ErrorActionPreference='Stop'
function Read-Env([string]$name){$v=[Environment]::GetEnvironmentVariable($name,'Machine');if(-not $v){$v=[Environment]::GetEnvironmentVariable($name,'User')};return $v}
$env:PGHOST=Read-Env 'GL02_PGHOST';$env:PGPORT=Read-Env 'GL02_PGPORT';$env:PGDATABASE=Read-Env 'GL02_PGDATABASE';$env:PGUSER=Read-Env 'GL02_PGUSER';$env:PGPASSWORD=Read-Env 'GL02_PGPASSWORD'
$psql='F:\PostgreSQL\16\bin\psql.exe'
$sql=@'
WITH wanted(variable_name) AS (VALUES ('Q_soft_water'),('P_soft_water'),('Q_high_pressure_water'),('P_high_pressure_water'),('P_medium_pressure_water'),('ExpansionTankLevel')),
rows AS (
 SELECT r.variable_name,count(*) FILTER(WHERE v.ts>='2026-07-10' AND v.ts<'2026-08-09') AS rows_window,
 count(DISTINCT v.ts::date) FILTER(WHERE v.ts>='2026-07-10' AND v.ts<'2026-08-09') AS days_present
 FROM wanted w JOIN bf_sensor.sensor_registry r USING(variable_name) LEFT JOIN bf_sensor.one_minute_values v USING(tag_long_name) GROUP BY r.variable_name
), base AS (
 SELECT DISTINCT ON(b.variable_name)b.variable_name,b.baseline_day,b.sample_count,b.coverage_ratio,b.median_ref,b.iqr_ref,b.p25,b.p75,b.updated_at
 FROM bf_sensor.daily_baselines b JOIN wanted w USING(variable_name) WHERE b.baseline_days=30 ORDER BY b.variable_name,b.baseline_day DESC,b.updated_at DESC
)
SELECT json_agg(json_build_object('variable_name',w.variable_name,'rows_window',r.rows_window,'days_present',r.days_present,'baseline_day',b.baseline_day,'sample_count',b.sample_count,'coverage_ratio',b.coverage_ratio,'median_ref',b.median_ref,'iqr_ref',b.iqr_ref,'p25',b.p25,'p75',b.p75,'updated_at',b.updated_at)ORDER BY w.variable_name)::text
FROM wanted w LEFT JOIN rows r USING(variable_name) LEFT JOIN base b USING(variable_name);
'@
&$psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if($LASTEXITCODE-ne0){throw 'final verification failed'}
