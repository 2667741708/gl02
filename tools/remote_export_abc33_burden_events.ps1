$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$psql = 'F:\PostgreSQL\16\bin\psql.exe'
$outputPath = 'C:\Users\Administrator\AppData\Local\Temp\abc33_burden_events.csv'
$dbPassword = [Environment]::GetEnvironmentVariable('GL02_PGADMIN_PASSWORD', 'Machine')
if ([string]::IsNullOrWhiteSpace($dbPassword)) {
    throw 'GL02_PGADMIN_PASSWORD is unavailable'
}

$env:PGPASSWORD = $dbPassword
try {
    $copySql = @"
\copy (
  SELECT workdate2::timestamp AS event_ts,
         COALESCE(NULLIF(charge,''), row_json->>'charge') AS charge,
         fetched_at,
         updated_at
  FROM bf_imes.raw_rows
  WHERE dataset_key='bf2_batch_input_detail_list_page_data2'
    AND workdate2 ~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
    AND workdate2::timestamp >= localtimestamp - interval '49 hours'
    AND workdate2::timestamp <= localtimestamp
  ORDER BY workdate2::timestamp
) TO '$($outputPath.Replace('\','/'))' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
"@
    & $psql -w -h 127.0.0.1 -p 5432 -U postgres -d bf_trend -X -v ON_ERROR_STOP=1 -c $copySql
    $file = Get-Item -LiteralPath $outputPath
    [pscustomobject]@{
        output_path = $file.FullName
        bytes = $file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    } | ConvertTo-Json -Compress
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
