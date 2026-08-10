$ErrorActionPreference = 'Stop'
$syncRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取'
$configPath = Join-Path $syncRoot 'config\sync_config.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$psql = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psql)) { $psql = 'F:\PostgreSQL\16\bin\psql.exe' }
$env:PGPASSWORD = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','Machine')
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','User') }
$user = [Environment]::GetEnvironmentVariable('GL02_PGUSER','Machine')
if (-not $user) { $user = [Environment]::GetEnvironmentVariable('GL02_PGUSER','User') }
if (-not $user) { $user = 'gl02_sync' }
$sql = @'
SELECT aggregate, interval_seconds, count(*) AS rows, min(ts) AS min_ts, max(ts) AS max_ts
FROM bf_sensor.one_minute_values GROUP BY aggregate, interval_seconds ORDER BY aggregate;
SELECT max(ts) AS max_ts, round(extract(epoch FROM (localtimestamp-max(ts)))::numeric/60,3) AS lag_min
FROM bf_sensor.one_minute_values;
SELECT variable_name, aggregate, interval_seconds, ts, value
FROM bf_sensor.v_one_minute_with_registry
WHERE variable_name IN ('BlastEnergy','Q_soft_water','CO_top','H2_top')
ORDER BY variable_name, ts DESC LIMIT 8;
'@
$sqlPath = Join-Path $env:TEMP 'foreman_minute_aggregate_probe.sql'
Set-Content -LiteralPath $sqlPath -Value $sql -Encoding UTF8
try {
    [ordered]@{
        source_mode = $config.source.source_mode
        source_aggregate = $config.source.source_aggregate
        target_aggregate = $config.source.target_aggregate
        target_interval_seconds = $config.source.target_interval_seconds
        continuous_poll_seconds = $config.sync.continuous_poll_seconds
        lookback_minutes = $config.sync.continuous_lookback_minutes
    } | ConvertTo-Json
    & $psql -h 127.0.0.1 -p 5432 -U $user -d bf_trend -v ON_ERROR_STOP=1 -f $sqlPath
    if ($LASTEXITCODE -ne 0) { throw "psql exit $LASTEXITCODE" }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $sqlPath -Force -ErrorAction SilentlyContinue
}
