$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$psql = 'F:\PostgreSQL\16\bin\psql.exe'
if (-not (Test-Path -LiteralPath $psql)) {
    throw "psql not found: $psql"
}

$dbPassword = [Environment]::GetEnvironmentVariable('GL02_PGADMIN_PASSWORD', 'Machine')
if ([string]::IsNullOrWhiteSpace($dbPassword)) {
    throw 'GL02_PGADMIN_PASSWORD is unavailable'
}

$env:PGPASSWORD = $dbPassword
try {
    & $psql -w -h 127.0.0.1 -p 5432 -U postgres -d bf_trend -X -v ON_ERROR_STOP=1 -P pager=off -c @'
SELECT dataset_key,
       count(*) AS row_count,
       min(workdate2) AS min_workdate2,
       max(workdate2) AS max_workdate2,
       max(updated_at) AS latest_update
FROM bf_imes.raw_rows
WHERE dataset_key LIKE 'bf2_batch%'
GROUP BY dataset_key
ORDER BY dataset_key;
'@

    & $psql -w -h 127.0.0.1 -p 5432 -U postgres -d bf_trend -X -v ON_ERROR_STOP=1 -P pager=off -c @'
SELECT dataset_key, workdate, workdate2, lot, charge,
       row_json->>'remark3' AS remark3,
       row_json->>'mining_batch_sum' AS mining_batch_sum,
       row_json->>'coke_charge_sum' AS coke_charge_sum,
       row_json->>'value_sum' AS value_sum,
       fetched_at, updated_at
FROM bf_imes.raw_rows
WHERE dataset_key IN (
    'bf2_batch_input_detail_list_page_data2',
    'bf2_batch_input_detail_list_page_data3',
    'bf2_batch_input_detail_list_page_data4',
    'bf2_batch_all_rows',
    'bf2_batch_mining',
    'bf2_batch_coke'
)
ORDER BY COALESCE(NULLIF(workdate2, '')::timestamp, workdate::timestamp) DESC
LIMIT 30;
'@

    & $psql -w -h 127.0.0.1 -p 5432 -U postgres -d bf_trend -X -v ON_ERROR_STOP=1 -P pager=off -c @'
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='bf_imes'
  AND (
      column_name ILIKE '%rate%'
      OR column_name ILIKE '%batch%'
      OR column_name ILIKE '%workdate2%'
  )
ORDER BY table_name, ordinal_position;
'@
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
