$ErrorActionPreference='Stop'
function Read-Env([string]$name){
  $v=[Environment]::GetEnvironmentVariable($name,'Machine')
  if(-not $v){$v=[Environment]::GetEnvironmentVariable($name,'User')}
  return $v
}
$env:PGHOST=Read-Env 'GL02_PGHOST'
$env:PGPORT=Read-Env 'GL02_PGPORT'
$env:PGDATABASE=Read-Env 'GL02_PGDATABASE'
$env:PGUSER=Read-Env 'GL02_PGUSER'
$env:PGPASSWORD=Read-Env 'GL02_PGPASSWORD'
$psql='F:\PostgreSQL\16\bin\psql.exe'
$sql=@'
WITH wanted(variable_name) AS (
 VALUES ('Q_soft_water'),('P_soft_water'),('Q_high_pressure_water'),
        ('P_high_pressure_water'),('P_medium_pressure_water'),('ExpansionTankLevel')
), days AS (
 SELECT generate_series(current_date-90,current_date-1,interval '1 day')::date AS day
), counts AS (
 SELECT r.variable_name,v.ts::date AS day,count(*) AS row_count
 FROM bf_sensor.sensor_registry r
 JOIN wanted w USING(variable_name)
 JOIN bf_sensor.one_minute_values v USING(tag_long_name)
 WHERE v.ts>=current_date-90 AND v.ts<current_date
 GROUP BY r.variable_name,v.ts::date
), summary AS (
 SELECT w.variable_name,
        coalesce(sum(c.row_count),0) AS rows_90d,
        count(c.day) AS days_with_rows,
        min(c.row_count) AS min_rows_per_present_day,
        max(c.row_count) AS max_rows_per_present_day,
        json_agg(d.day ORDER BY d.day) FILTER(WHERE c.day IS NULL) AS missing_days
 FROM wanted w CROSS JOIN days d
 LEFT JOIN counts c ON c.variable_name=w.variable_name AND c.day=d.day
 GROUP BY w.variable_name
)
SELECT json_agg(summary ORDER BY variable_name)::text FROM summary;
'@
&$psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if($LASTEXITCODE-ne0){throw '90-day completeness verification failed'}
