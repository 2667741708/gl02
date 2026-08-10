$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Get-EnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    foreach ($scope in @('Machine', 'User', 'Process')) {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if ($value) { return $value }
    }
    return $null
}

$psqlCandidates = @(
    'F:\PostgreSQL\16\bin\psql.exe',
    'C:\Program Files\PostgreSQL\16\bin\psql.exe'
)
$psql = $psqlCandidates | Where-Object {
    Test-Path -LiteralPath $_ -PathType Leaf
} | Select-Object -First 1
if (-not $psql) { throw 'PostgreSQL psql executable was not found.' }

$env:PGPASSWORD = Get-EnvironmentValue -Name 'GL02_PGPASSWORD'
$pgUser = Get-EnvironmentValue -Name 'GL02_PGUSER'
if (-not $pgUser) { $pgUser = 'gl02_sync' }

$sql = @'
\pset pager off
SET statement_timeout = '30s';

SELECT dataset_key,
       count(*) AS rows,
       max(COALESCE(fetched_at, updated_at)) AS latest_fetch
FROM bf_imes.raw_rows
WHERE dataset_key ~ '(output|input|dosing|batch)'
GROUP BY dataset_key
ORDER BY dataset_key;

WITH recent AS (
    SELECT dataset_key, row_json, fetched_at, updated_at
    FROM bf_imes.raw_rows
    WHERE dataset_key IN (
        'bf2_output_list_cond_data',
        'bf2_dosing_scheme_list_page_data'
    )
      AND COALESCE(workdate, updated_at::date) >= current_date - 30
), fields AS (
    SELECT r.dataset_key,
           entry.key,
           entry.value,
           COALESCE(r.fetched_at, r.updated_at) AS observed_at
    FROM recent r
    CROSS JOIN LATERAL jsonb_each_text(r.row_json) AS entry(key, value)
)
SELECT dataset_key,
       key,
       count(*) AS observations,
       max(observed_at) AS latest_observed,
       left(max(value), 120) AS sample_value
FROM fields
WHERE lower(key) LIKE ANY (ARRAY[
          '%fuel%', '%ratio%', '%speed%', '%burden%',
          '%coke%', '%coal%', '%material%', '%charge%'
      ])
   OR position('料速' in value) > 0
   OR position('燃料比' in value) > 0
   OR position('综合燃料比' in value) > 0
   OR position('焦比' in value) > 0
   OR position('煤比' in value) > 0
GROUP BY dataset_key, key
ORDER BY dataset_key, key;

SELECT DISTINCT field.key
FROM bf_imes.raw_rows r
CROSS JOIN LATERAL jsonb_object_keys(r.row_json) AS field(key)
WHERE r.dataset_key = 'bf2_output_list_cond_data'
ORDER BY field.key;

WITH sampled AS (
    (SELECT dataset_key, row_json
     FROM bf_imes.raw_rows
     WHERE dataset_key = 'bf2_batch_input_detail_list_page_data2'
     LIMIT 1)
    UNION ALL
    (SELECT dataset_key, row_json
     FROM bf_imes.raw_rows
     WHERE dataset_key = 'bf2_batch_input_detail_list_page_data3'
     LIMIT 1)
    UNION ALL
    (SELECT dataset_key, row_json
     FROM bf_imes.raw_rows
     WHERE dataset_key = 'bf2_batch_input_detail_list_page_data4'
     LIMIT 1)
    UNION ALL
    (SELECT dataset_key, row_json
     FROM bf_imes.raw_rows
     WHERE dataset_key = 'bf2_dosing_scheme_list_page_data'
     LIMIT 1)
    UNION ALL
    (SELECT dataset_key, row_json
     FROM bf_imes.raw_rows
     WHERE dataset_key = 'bf2_input_list_page_data'
     LIMIT 1)
), sample_fields AS (
    SELECT sampled.dataset_key,
           entry.key,
           entry.value
    FROM sampled
    CROSS JOIN LATERAL jsonb_each_text(sampled.row_json) AS entry(key, value)
)
SELECT dataset_key,
       key,
       left(max(value), 100) AS sample_value
FROM sample_fields
GROUP BY dataset_key, key
ORDER BY dataset_key, key;
'@

$sql | & $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) {
    throw "IMES metric-field audit failed with psql exit code $LASTEXITCODE"
}
