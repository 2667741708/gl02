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

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'bf_imes'
  AND table_name ~ '(heat|output|cond|performance|quality)'
ORDER BY table_name;

SELECT "meltNo" AS meltno,
       "workDate" AS work_date,
       "openTime" AS open_ts,
       "closeTime" AS close_ts,
       "value_02" AS si,
       "batchno" AS batchno
FROM bf_imes.imes_bf2_output_list_cond_data
WHERE "meltNo" LIKE '2#%'
ORDER BY substring("meltNo" from '([0-9]+)$')::integer DESC,
         "openTime" DESC NULLS LAST
LIMIT 20;

SELECT dataset_key,
       count(*) AS rows,
       max(COALESCE(fetched_at, updated_at)) AS latest_fetch,
       max(COALESCE(row_json->>'meltNo', row_json->>'meltno')) AS max_meltno
FROM bf_imes.raw_rows
WHERE COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE '2#%'
GROUP BY dataset_key
ORDER BY latest_fetch DESC NULLS LAST;

SELECT dataset_key,
       COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
       row_json,
       COALESCE(fetched_at, updated_at) AS mirrored_at
FROM bf_imes.raw_rows
WHERE dataset_key IN (
        'bf2_output_list_cond_data',
        'bf2_heat_lab_list_cond_data_avg2',
        'bf2_heat_lab_all_list_cond_data_avg2_new'
      )
  AND COALESCE(row_json->>'meltNo', row_json->>'meltno') IN (
        '2#20260808-110', '2#20260808-111',
        '2#20260808-112', '2#20260808-113'
      )
ORDER BY meltno, dataset_key;
'@

$sqlPath = Join-Path ([IO.Path]::GetTempPath()) 'audit_latest_heat_candidates.sql'
try {
    [IO.File]::WriteAllText($sqlPath, $sql, [Text.UTF8Encoding]::new($false))
    & $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=1 -f $sqlPath
    if ($LASTEXITCODE -ne 0) {
        throw "Latest heat candidate audit failed with psql exit code $LASTEXITCODE"
    }
}
finally {
    if (Test-Path -LiteralPath $sqlPath) {
        Remove-Item -LiteralPath $sqlPath -Force
    }
}
