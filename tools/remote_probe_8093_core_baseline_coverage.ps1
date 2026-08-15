[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

function Read-EnvValue {
    param([string]$Name)
    $Value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
    if (-not $Value) { $Value = [Environment]::GetEnvironmentVariable($Name, 'User') }
    return $Value
}

$env:PGHOST = Read-EnvValue -Name 'GL02_PGHOST'
$env:PGPORT = Read-EnvValue -Name 'GL02_PGPORT'
$env:PGDATABASE = Read-EnvValue -Name 'GL02_PGDATABASE'
$env:PGUSER = Read-EnvValue -Name 'GL02_PGUSER'
$env:PGPASSWORD = Read-EnvValue -Name 'GL02_PGPASSWORD'
foreach ($Name in @('PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD')) {
    if (-not (Get-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue).Value) {
        throw "Missing PostgreSQL environment: $Name"
    }
}

$Psql = 'F:\PostgreSQL\16\bin\psql.exe'
if (-not (Test-Path -LiteralPath $Psql -PathType Leaf)) { throw 'psql not found.' }

$Sql = @'
WITH expected(variable_name) AS (
  VALUES ('P_top'),('P_top_gas_A'),('P_top_gas_B'),('P_top_gas_C'),('P_top_gas_D'),
         ('GasUtil'),('TFT'),('T_blast'),('T_top_A'),('T_top_B'),('T_top_C'),('T_top_D'),
         ('Q_blast'),('P_blast_cold'),('P_blast'),('O2_rate'),('Q_O2'),('PI'),
         ('DP_upper'),('DP_lower'),('DP_total'),('L'),('L_south'),('L_north'),
         ('PCI_rate'),('PCI_set'),('T_taphole_1'),('T_taphole_2')
), latest_global AS (
  SELECT max(baseline_day) AS day FROM bf_sensor.daily_baselines WHERE baseline_days=30
), latest_per_variable AS (
  SELECT DISTINCT ON (variable_name) variable_name,baseline_day,median_ref,iqr_ref,sample_count,coverage_ratio
  FROM bf_sensor.daily_baselines
  WHERE baseline_days=30 AND variable_name IN (SELECT variable_name FROM expected)
  ORDER BY variable_name,baseline_day DESC,updated_at DESC
), on_global_day AS (
  SELECT variable_name FROM bf_sensor.daily_baselines,latest_global
  WHERE baseline_days=30 AND baseline_day=latest_global.day AND variable_name IN (SELECT variable_name FROM expected)
)
SELECT json_build_object(
  'latest_global_day',(SELECT day FROM latest_global),
  'expected_count',(SELECT count(*) FROM expected),
  'global_day_count',(SELECT count(DISTINCT variable_name) FROM on_global_day),
  'latest_per_variable_count',(SELECT count(*) FROM latest_per_variable),
  'missing',coalesce((SELECT json_agg(e.variable_name ORDER BY e.variable_name) FROM expected e LEFT JOIN latest_per_variable l USING(variable_name) WHERE l.variable_name IS NULL),'[]'::json),
  'items',coalesce((SELECT json_agg(json_build_object('id',variable_name,'day',baseline_day,'median',median_ref,'iqr',iqr_ref,'sample_count',sample_count,'coverage_ratio',coverage_ratio) ORDER BY variable_name) FROM latest_per_variable),'[]'::json)
)::text;
'@

$Json = & $Psql -X -q -t -A -v ON_ERROR_STOP=1 -c $Sql
if ($LASTEXITCODE -ne 0) { throw 'Core baseline coverage query failed.' }
$Json
