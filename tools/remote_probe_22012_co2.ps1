$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
    throw "psql not found: $psql"
}

$pgHost = [Environment]::GetEnvironmentVariable("GL02_PGHOST", "Machine")
$pgPort = [Environment]::GetEnvironmentVariable("GL02_PGPORT", "Machine")
$pgDatabase = [Environment]::GetEnvironmentVariable("GL02_PGDATABASE", "Machine")
$pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
$pgPassword = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")

if (-not $pgHost) { $pgHost = "127.0.0.1" }
if (-not $pgPort) { $pgPort = "5432" }
if (-not $pgDatabase) { $pgDatabase = "bf_trend" }
if (-not $pgUser -or -not $pgPassword) {
    throw "GL02 PostgreSQL machine credentials are unavailable"
}

$registrySql = @"
SELECT variable_name, short_name, tag_long_name, description, is_enabled
FROM bf_sensor.sensor_registry
WHERE variable_name IN ('CO_top','CO2_top','H2_top','BlastEnergy','BlastSpeedStd','BlastSpeedActual')
   OR short_name IN ('CO_top','CO2_top','H2_top','BlastEnergy','BlastSpeedStd','BlastSpeedActual')
ORDER BY variable_name;
"@

$latestSql = @"
SELECT r.variable_name, r.short_name, v.ts, v.value, v.quality, v.aggregate, v.source_server
FROM bf_sensor.sensor_registry r
LEFT JOIN LATERAL (
    SELECT ts, value, quality, aggregate, source_server
    FROM bf_sensor.one_minute_values
    WHERE tag_long_name = r.tag_long_name
    ORDER BY ts DESC
    LIMIT 1
) v ON true
WHERE r.variable_name IN ('CO_top','CO2_top','H2_top','BlastEnergy','BlastSpeedStd','BlastSpeedActual')
   OR r.short_name IN ('CO_top','CO2_top','H2_top','BlastEnergy','BlastSpeedStd','BlastSpeedActual')
ORDER BY r.variable_name;
"@

$syncStateSql = @"
SELECT r.variable_name, s.last_success_ts, s.last_attempt_ts,
       (NULLIF(s.last_error, '') IS NOT NULL) AS has_error
FROM bf_sensor.sensor_registry r
LEFT JOIN bf_sensor.sync_state s ON s.tag_long_name = r.tag_long_name
WHERE r.variable_name IN ('CO_top','CO2_top','H2_top','BlastEnergy','BlastSpeedStd','BlastSpeedActual')
ORDER BY r.variable_name;
"@

$syncRunsSql = @"
SELECT id, started_at, finished_at, sync_mode, start_ts, end_ts, rows_written, tags_ok, tags_error, error
FROM bf_sensor.sync_runs
ORDER BY id DESC
LIMIT 5;
"@

$env:PGPASSWORD = $pgPassword
try {
    Write-Output "REGISTRY"
    & $psql -w -X -h $pgHost -p $pgPort -U $pgUser -d $pgDatabase --csv -c $registrySql
    if ($LASTEXITCODE -ne 0) { throw "registry query failed: $LASTEXITCODE" }

    Write-Output "LATEST"
    & $psql -w -X -h $pgHost -p $pgPort -U $pgUser -d $pgDatabase --csv -c $latestSql
    if ($LASTEXITCODE -ne 0) { throw "latest query failed: $LASTEXITCODE" }

    Write-Output "SYNC_STATE"
    & $psql -w -X -h $pgHost -p $pgPort -U $pgUser -d $pgDatabase --csv -c $syncStateSql
    if ($LASTEXITCODE -ne 0) { throw "sync state query failed: $LASTEXITCODE" }

    Write-Output "SYNC_RUNS"
    & $psql -w -X -h $pgHost -p $pgPort -U $pgUser -d $pgDatabase --csv -c $syncRunsSql
    if ($LASTEXITCODE -ne 0) { throw "sync runs query failed: $LASTEXITCODE" }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
