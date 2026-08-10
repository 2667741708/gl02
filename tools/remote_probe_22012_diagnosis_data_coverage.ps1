$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Read-MachineOrUserEnvironment([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
    }
    return $value
}

$hostName = Read-MachineOrUserEnvironment "GL02_PGHOST"
$port = Read-MachineOrUserEnvironment "GL02_PGPORT"
$database = Read-MachineOrUserEnvironment "GL02_PGDATABASE"
$runtimeUser = Read-MachineOrUserEnvironment "GL02_PGUSER"
$runtimePassword = Read-MachineOrUserEnvironment "GL02_PGPASSWORD"
$readerPassword = Read-MachineOrUserEnvironment "GL02_READER_PASSWORD"

foreach ($name in @("GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD")) {
    if (-not (Read-MachineOrUserEnvironment $name)) {
        throw "Missing remote PostgreSQL environment variable: $name"
    }
}

$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
    throw "psql not found: $psql"
}

$query = @"
WITH target AS (
    SELECT max(diagnosis_ts) AS diagnosis_ts
    FROM bf_sensor.diagnosis_snapshots
), vars(variable_name) AS (
    VALUES ('L_north'), ('L_south'), ('T_top_A'), ('T_top_B'), ('T_top_C'), ('T_top_D')
), rows_in_window AS (
    SELECT r.variable_name, v.ts, v.value,
           COALESCE(z.verification_status, '') AS verification_status
    FROM bf_sensor.one_minute_values v
    JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
    LEFT JOIN bf_sensor.zero_value_audits z
      ON z.tag_long_name = v.tag_long_name
     AND z.ts = v.ts
     AND z.pspace_aggregate = v.aggregate
    CROSS JOIN target
    WHERE r.variable_name IN (SELECT variable_name FROM vars)
      AND v.ts >= target.diagnosis_ts - interval '60 minutes'
      AND v.ts <= target.diagnosis_ts
)
SELECT json_build_object(
    'variable_name', vars.variable_name,
    'registry', (
        SELECT json_agg(json_build_object(
            'tag_long_name', r.tag_long_name,
            'is_enabled', r.is_enabled,
            'is_derived', r.is_derived
        ) ORDER BY r.tag_long_name)
        FROM bf_sensor.sensor_registry r
        WHERE r.variable_name = vars.variable_name
    ),
    'latest_diagnosis_ts', (SELECT diagnosis_ts FROM target),
    'window_rows', (SELECT count(*) FROM rows_in_window w WHERE w.variable_name = vars.variable_name),
    'distinct_minutes', (SELECT count(DISTINCT date_trunc('minute', w.ts)) FROM rows_in_window w WHERE w.variable_name = vars.variable_name),
    'non_null_values', (SELECT count(*) FROM rows_in_window w WHERE w.variable_name = vars.variable_name AND w.value IS NOT NULL),
    'raw_zero_values', (SELECT count(*) FROM rows_in_window w WHERE w.variable_name = vars.variable_name AND w.value = 0),
    'unverified_zero_values', (SELECT count(*) FROM rows_in_window w WHERE w.variable_name = vars.variable_name AND w.value = 0 AND w.verification_status <> 'verified_zero'),
    'min_ts', (SELECT min(w.ts) FROM rows_in_window w WHERE w.variable_name = vars.variable_name),
    'max_ts', (SELECT max(w.ts) FROM rows_in_window w WHERE w.variable_name = vars.variable_name),
    'accepted_rows_by_current_query', (SELECT count(*) FROM rows_in_window w WHERE w.variable_name = vars.variable_name AND NOT (w.value = 0 AND w.verification_status <> 'verified_zero'))
)::text
FROM vars
ORDER BY vars.variable_name;
"@

$coverageQuery = @"
SELECT json_build_object(
    'diagnosis_ts', diagnosis_ts,
    'main_label', main_label,
    'data_coverage', data_coverage,
    'missing_variables', missing_variables
)::text
FROM bf_sensor.diagnosis_snapshots
ORDER BY diagnosis_ts DESC, id DESC
LIMIT 1;
"@

$baselineQuery = @"
SELECT json_build_object(
    'variable_name', variable_name,
    'baseline_day', baseline_day,
    'sample_count', sample_count,
    'coverage_ratio', coverage_ratio,
    'baseline_window_start', baseline_window_start,
    'baseline_window_end', baseline_window_end
)::text
FROM (
    SELECT DISTINCT ON (variable_name)
           variable_name, baseline_day, sample_count, coverage_ratio,
           baseline_window_start, baseline_window_end
    FROM bf_sensor.daily_baselines
    WHERE baseline_days = 30
      AND variable_name IN ('L_north', 'L_south', 'T_top_A', 'T_top_B', 'T_top_C', 'T_top_D')
    ORDER BY variable_name, baseline_day DESC, updated_at DESC
) latest
ORDER BY variable_name;
"@

$sourceQualityQuery = @"
WITH target AS (
    SELECT max(diagnosis_ts) AS diagnosis_ts
    FROM bf_sensor.diagnosis_snapshots
), vars(variable_name) AS (
    VALUES ('L_north'), ('L_south'), ('T_top_A'), ('T_top_B'), ('T_top_C'), ('T_top_D')
), tags AS (
    SELECT r.variable_name, r.tag_long_name
    FROM bf_sensor.sensor_registry r
    WHERE r.variable_name IN (SELECT variable_name FROM vars)
), minute_quality AS (
    SELECT t.variable_name,
           count(v.*) AS minute_rows,
           count(*) FILTER (WHERE v.window_complete) AS complete_minute_rows,
           min(v.sample_count) AS min_sample_count,
           max(v.sample_count) AS max_sample_count,
           min(v.coverage_ratio) AS min_minute_coverage,
           avg(v.coverage_ratio) AS avg_minute_coverage,
           max(v.coverage_ratio) AS max_minute_coverage
    FROM tags t
    LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name = t.tag_long_name
    CROSS JOIN target
    WHERE v.ts >= target.diagnosis_ts - interval '60 minutes'
      AND v.ts <= target.diagnosis_ts
    GROUP BY t.variable_name
), raw_quality AS (
    SELECT t.variable_name,
           count(v.*) AS raw_5s_rows,
           count(DISTINCT date_trunc('minute', v.ts)) AS raw_5s_minutes,
           min(v.ts) AS raw_min_ts,
           max(v.ts) AS raw_max_ts
    FROM tags t
    LEFT JOIN bf_sensor.raw_5s_values v ON v.tag_long_name = t.tag_long_name
    CROSS JOIN target
    WHERE v.ts >= target.diagnosis_ts - interval '60 minutes'
      AND v.ts <= target.diagnosis_ts
    GROUP BY t.variable_name
)
SELECT json_build_object(
    'variable_name', vars.variable_name,
    'minute_quality', (
        SELECT row_to_json(q) FROM minute_quality q WHERE q.variable_name = vars.variable_name
    ),
    'raw_5s_quality', (
        SELECT row_to_json(q) FROM raw_quality q WHERE q.variable_name = vars.variable_name
    )
)::text
FROM vars
ORDER BY vars.variable_name;
"@

function Invoke-ReadOnlyQuery([string]$Sql) {
    $env:PGPASSWORD = if ($readerPassword) { $readerPassword } else { $runtimePassword }
    try {
        $rows = & $psql -w -h $hostName -p $port -U $(if ($readerPassword) { "gl02_reader" } else { $runtimeUser }) -d $database -tA -v ON_ERROR_STOP=1 -c $Sql
        if ($LASTEXITCODE -ne 0) {
            throw "PostgreSQL read-only query failed with exit code $LASTEXITCODE"
        }
        return @($rows)
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
}

Write-Output "=== latest_diagnosis_coverage ==="
Invoke-ReadOnlyQuery $coverageQuery
Write-Output "=== variable_coverage_last_60m ==="
Invoke-ReadOnlyQuery $query
Write-Output "=== latest_30d_baselines ==="
Invoke-ReadOnlyQuery $baselineQuery
Write-Output "=== source_quality_last_60m ==="
Invoke-ReadOnlyQuery $sourceQualityQuery
