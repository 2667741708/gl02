$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Read-Env([string]$name) {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, "User") }
    return $value
}

$env:PGHOST = Read-Env "GL02_PGHOST"
$env:PGPORT = Read-Env "GL02_PGPORT"
$env:PGDATABASE = Read-Env "GL02_PGDATABASE"
$env:PGUSER = Read-Env "GL02_PGUSER"
$env:PGPASSWORD = Read-Env "GL02_PGPASSWORD"
foreach ($name in @("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")) {
    if (-not (Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue).Value) {
        throw "Missing PostgreSQL environment: $name"
    }
}

$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) { throw "psql not found" }

$sql = @'
WITH expected(variable_name, source_kind) AS (
    VALUES
    ('P_top','sensor'),('DP_total','sensor'),('DP_upper','sensor'),('DP_lower','sensor'),
    ('Q_blast','sensor'),('P_blast','sensor'),('P_blast_cold','sensor'),('PI','sensor'),('GasUtil','sensor'),
    ('T_top_A','sensor'),('T_top_B','sensor'),('T_top_C','sensor'),('T_top_D','sensor'),
    ('P_top_gas_A','sensor'),('P_top_gas_B','sensor'),('P_top_gas_C','sensor'),('P_top_gas_D','sensor'),
    ('L','sensor'),('L_south','sensor'),('L_north','sensor'),('Hopper_weight','sensor'),
    ('T_taphole_1','sensor'),('T_taphole_2','sensor'),('PCI_rate','sensor'),('O2_rate','sensor'),
    ('Q_O2','sensor'),('T_blast','sensor'),('TFT','sensor'),('BlastEnergy','sensor'),
    ('Q_soft_water','sensor'),('P_soft_water','sensor'),('Q_high_pressure_water','sensor'),
    ('P_high_pressure_water','sensor'),('P_medium_pressure_water','sensor'),('ExpansionTankLevel','sensor'),
    ('Q_N2','sensor'),('P_N2','sensor'),
    ('T_taphole_mean','derived'),('T_top','derived')
), registry AS (
    SELECT r.variable_name,
           count(*) AS registry_rows,
           count(*) FILTER (WHERE r.is_enabled) AS enabled_rows,
           bool_or(r.is_derived) AS registry_derived
    FROM bf_sensor.sensor_registry r
    JOIN expected e USING(variable_name)
    GROUP BY r.variable_name
), latest AS (
    SELECT r.variable_name, min(v.ts) AS first_ts, max(v.ts) AS latest_ts,
           count(*) FILTER (WHERE v.ts >= now()-interval '90 days') AS rows_90d,
           count(DISTINCT date_trunc('minute',v.ts)) FILTER (WHERE v.ts >= now()-interval '60 minutes') AS minutes_60m
    FROM bf_sensor.sensor_registry r
    JOIN expected e USING(variable_name)
    LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name=r.tag_long_name
    GROUP BY r.variable_name
), baseline AS (
    SELECT DISTINCT ON (b.variable_name) b.variable_name,b.baseline_day,b.baseline_days,b.median_ref,b.iqr_ref,
           b.p25,b.p75,b.sample_count,b.coverage_ratio,b.baseline_window_start,b.baseline_window_end,b.updated_at
    FROM bf_sensor.daily_baselines b
    JOIN expected e USING(variable_name)
    WHERE b.baseline_days=30
    ORDER BY b.variable_name,b.baseline_day DESC,b.updated_at DESC
)
SELECT json_build_object(
    'checked_at',now(),
    'items',json_agg(json_build_object(
        'variable_name',e.variable_name,'source_kind',e.source_kind,
        'registry_rows',coalesce(r.registry_rows,0),'enabled_rows',coalesce(r.enabled_rows,0),
        'registry_derived',coalesce(r.registry_derived,false),
        'first_ts',l.first_ts,'latest_ts',l.latest_ts,'rows_90d',coalesce(l.rows_90d,0),
        'minutes_60m',coalesce(l.minutes_60m,0),
        'baseline_day',b.baseline_day,'baseline_days',b.baseline_days,'median_ref',b.median_ref,'iqr_ref',b.iqr_ref,
        'p25',b.p25,'p75',b.p75,'sample_count',b.sample_count,'coverage_ratio',b.coverage_ratio,
        'baseline_window_start',b.baseline_window_start,'baseline_window_end',b.baseline_window_end,'baseline_updated_at',b.updated_at
    ) ORDER BY e.variable_name)
)::text
FROM expected e
LEFT JOIN registry r USING(variable_name)
LEFT JOIN latest l USING(variable_name)
LEFT JOIN baseline b USING(variable_name);
'@

$coreJson = & $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $sql
if ($LASTEXITCODE -ne 0) { throw "ABC core audit SQL failed" }

$familySql = @'
WITH families AS (
  SELECT 'static_pressure' AS family, count(DISTINCT variable_name) AS registry_variables,
         count(DISTINCT variable_name) FILTER (WHERE is_enabled) AS enabled_variables
  FROM bf_sensor.sensor_registry WHERE variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
  UNION ALL
  SELECT 'body_temperature',count(DISTINCT variable_name),count(DISTINCT variable_name) FILTER (WHERE is_enabled)
  FROM bf_sensor.sensor_registry WHERE variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$'
), latest AS (
  SELECT CASE WHEN r.variable_name ~ '^P_static_' THEN 'static_pressure' ELSE 'body_temperature' END AS family,
         count(DISTINCT r.variable_name) FILTER (WHERE v.ts >= now()-interval '10 minutes') AS variables_latest_10m,
         count(DISTINCT r.variable_name) FILTER (WHERE v.ts >= now()-interval '90 days') AS variables_90d
  FROM bf_sensor.sensor_registry r LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name=r.tag_long_name
  WHERE r.variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
     OR r.variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$'
  GROUP BY 1
), baselines AS (
  SELECT CASE WHEN variable_name ~ '^P_static_' THEN 'static_pressure' ELSE 'body_temperature' END AS family,
         count(DISTINCT variable_name) FILTER (WHERE baseline_day=(SELECT max(baseline_day) FROM bf_sensor.daily_baselines WHERE baseline_days=30)) AS variables_latest_baseline
  FROM bf_sensor.daily_baselines
  WHERE baseline_days=30 AND (variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$' OR variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$')
  GROUP BY 1
)
SELECT json_agg(json_build_object('family',f.family,'registry_variables',f.registry_variables,
 'enabled_variables',f.enabled_variables,'variables_latest_10m',coalesce(l.variables_latest_10m,0),
 'variables_90d',coalesce(l.variables_90d,0),'variables_latest_baseline',coalesce(b.variables_latest_baseline,0)) ORDER BY f.family)::text
FROM families f LEFT JOIN latest l USING(family) LEFT JOIN baselines b USING(family);
'@

$familyJson = & $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $familySql
if ($LASTEXITCODE -ne 0) { throw "ABC family audit SQL failed" }

$tasks = Get-ScheduledTask | Where-Object {
    $_.TaskName -match 'baseline' -or $_.Actions.Execute -match 'baseline' -or $_.Actions.Arguments -match 'baseline_maintainer'
} | ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath
    [pscustomobject]@{
        task_path = "$($_.TaskPath)$($_.TaskName)"
        state = [string]$_.State
        last_run_time = $info.LastRunTime
        last_task_result = $info.LastTaskResult
        next_run_time = $info.NextRunTime
        execute = ($_.Actions | ForEach-Object Execute) -join ';'
        arguments = ($_.Actions | ForEach-Object Arguments) -join ';'
    }
}

$processes = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'baseline_maintainer|run_v4_daily_baseline' } |
    Select-Object ProcessId,Name,CommandLine

$result = [pscustomobject]@{
    host = $env:COMPUTERNAME
    core = ($coreJson | ConvertFrom-Json)
    families = ($familyJson | ConvertFrom-Json)
    baseline_tasks = @($tasks)
    baseline_processes = @($processes)
} | ConvertTo-Json -Depth 10
$result
$result | Set-Content -LiteralPath "C:\Users\Administrator\AppData\Local\Temp\abc33_variables_baselines_audit.json" -Encoding UTF8
