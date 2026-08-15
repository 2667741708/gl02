[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

function Get-EnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    foreach ($scope in 'Machine', 'User', 'Process') {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if ($value) {
            return $value
        }
    }
    return $null
}

$PsqlCandidates = @(
    'F:\PostgreSQL\16\bin\psql.exe',
    'C:\Program Files\PostgreSQL\16\bin\psql.exe',
    'F:\PostgreSQL\15\bin\psql.exe',
    'C:\Program Files\PostgreSQL\15\bin\psql.exe'
)
$Psql = $PsqlCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Psql) {
    throw 'PostgreSQL psql executable was not found.'
}

$env:PGPASSWORD = Get-EnvironmentValue -Name 'GL02_PGPASSWORD'
$PgUser = Get-EnvironmentValue -Name 'GL02_PGUSER'
if (-not $PgUser) {
    $PgUser = 'gl02_sync'
}

$Sql = @'
\pset pager off
\echo ===== FOREMAN REGISTRY =====
WITH wanted(variable_name, display_name) AS (
    VALUES
      ('P_top', '综合顶压'),
      ('DP_total', '全炉压差'),
      ('P_blast', '热风压力'),
      ('T_blast', '热风温度'),
      ('Q_blast', '冷风流量'),
      ('PCI_rate', '喷煤实际速率'),
      ('GasUtil', '煤气利用率'),
      ('PI', '透气性指数'),
      ('T_top', '荒煤气温度'),
      ('L', '雷达探尺'),
      ('Q_O2', '富氧流量'),
      ('O2_rate', '富氧率'),
      ('Hopper_weight_set', '罐重设定'),
      ('Hopper_weight', '罐重'),
      ('L_south', '南尺'),
      ('L_north', '北尺')
)
SELECT w.variable_name,
       w.display_name,
       r.short_name,
       r.tag_long_name,
       r.description,
       r.is_derived,
       r.is_enabled,
       r.updated_at
FROM wanted w
LEFT JOIN bf_sensor.sensor_registry r USING (variable_name)
ORDER BY w.variable_name;

\echo ===== VALUES NEAR SCREENSHOT 2026-08-14 06:27 =====
WITH wanted(variable_name) AS (
    VALUES ('P_top'), ('DP_total'), ('P_blast'), ('T_blast'), ('Q_blast'),
           ('PCI_rate'), ('GasUtil'), ('PI'), ('T_top'), ('L'), ('Q_O2'),
           ('O2_rate'), ('Hopper_weight_set'), ('Hopper_weight'), ('L_south'), ('L_north')
)
SELECT w.variable_name,
       r.short_name,
       h.ts,
       round(h.value::numeric, 6) AS value,
       h.quality,
       h.aggregate,
       h.interval_seconds,
       h.coverage_ratio
FROM wanted w
LEFT JOIN bf_sensor.sensor_registry r USING (variable_name)
LEFT JOIN LATERAL (
    SELECT v.*
    FROM bf_sensor.one_minute_values v
    WHERE v.tag_long_name = r.tag_long_name
      AND v.ts BETWEEN timestamp '2026-08-14 06:25:00' AND timestamp '2026-08-14 06:29:00'
    ORDER BY abs(extract(epoch FROM (v.ts - timestamp '2026-08-14 06:27:00')))
    LIMIT 1
) h ON true
ORDER BY w.variable_name;

\echo ===== TWO-HOUR RANGES 06:00-08:00 =====
WITH wanted(variable_name) AS (
    VALUES ('P_top'), ('DP_total'), ('P_blast'), ('T_blast'), ('Q_blast'),
           ('PCI_rate'), ('GasUtil'), ('PI'), ('T_top'), ('L'), ('Q_O2'),
           ('O2_rate'), ('Hopper_weight_set'), ('Hopper_weight'), ('L_south'), ('L_north')
)
SELECT w.variable_name,
       r.short_name,
       count(v.value) AS points,
       round(min(v.value)::numeric, 4) AS min_value,
       round(avg(v.value)::numeric, 4) AS avg_value,
       round(max(v.value)::numeric, 4) AS max_value
FROM wanted w
LEFT JOIN bf_sensor.sensor_registry r USING (variable_name)
LEFT JOIN bf_sensor.one_minute_values v
  ON v.tag_long_name = r.tag_long_name
 AND v.ts >= timestamp '2026-08-14 06:00:00'
 AND v.ts < timestamp '2026-08-14 08:00:00'
GROUP BY w.variable_name, r.short_name
ORDER BY w.variable_name;

\echo ===== TAGS MATCHING SCREENSHOT VALUE 22.381 =====
SELECT r.variable_name,
       r.short_name,
       r.description,
       v.ts,
       round(v.value::numeric, 6) AS value
FROM bf_sensor.one_minute_values v
LEFT JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
WHERE v.ts BETWEEN timestamp '2026-08-14 06:26:00' AND timestamp '2026-08-14 06:28:00'
  AND abs(v.value - 22.381) < 0.1
ORDER BY abs(v.value - 22.381), v.ts;

\echo ===== LATEST FOREMAN VALUES =====
WITH wanted(variable_name) AS (
    VALUES ('P_top'), ('DP_total'), ('P_blast'), ('T_blast'), ('Q_blast'),
           ('PCI_rate'), ('GasUtil'), ('PI'), ('T_top'), ('L'), ('Q_O2'),
           ('O2_rate'), ('Hopper_weight_set'), ('Hopper_weight'), ('L_south'), ('L_north')
)
SELECT w.variable_name,
       r.short_name,
       latest.ts,
       round(latest.value::numeric, 6) AS value,
       latest.quality
FROM wanted w
LEFT JOIN bf_sensor.sensor_registry r USING (variable_name)
LEFT JOIN LATERAL (
    SELECT v.ts, v.value, v.quality
    FROM bf_sensor.one_minute_values v
    WHERE v.tag_long_name = r.tag_long_name
    ORDER BY v.ts DESC
    LIMIT 1
) latest ON true
ORDER BY w.variable_name;
'@

$SqlPath = Join-Path $env:TEMP ("foreman_curve_mapping_{0}.sql" -f [guid]::NewGuid().ToString('N'))
try {
    Set-Content -LiteralPath $SqlPath -Value $Sql -Encoding UTF8
    & $Psql -h 127.0.0.1 -p 5432 -U $PgUser -d bf_trend -v ON_ERROR_STOP=1 -f $SqlPath
    if ($LASTEXITCODE -ne 0) {
        throw "Foreman mapping audit failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $SqlPath -Force -ErrorAction SilentlyContinue
}
