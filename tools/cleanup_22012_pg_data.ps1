param(
    [datetime]$Before,
    [datetime]$After,
    [ValidateSet("raw5s", "minute", "diagnosis", "quality", "automation", "zero_audit", "backfill")]
    [string[]]$Targets = @("raw5s"),
    [switch]$Execute,
    [switch]$IUnderstandProductionDelete,
    [switch]$VacuumAnalyze,
    [string]$RemoteRoot = "F:\高炉炼铁项目-real-sensor-v2_V3"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if (-not $Before -and -not $After) {
    throw "Please provide -Before, -After, or both. Example: -Before '2026-05-13 00:00:00'"
}
if ($Execute -and -not $IUnderstandProductionDelete) {
    throw "Refusing to delete production data. Add -IUnderstandProductionDelete together with -Execute."
}
if ($Before -and $After -and $After -ge $Before) {
    throw "-After must be earlier than -Before when both are provided."
}

$ToolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ToolsDir
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
$RemoteExec = Join-Path $ToolsDir "remote_22012_exec.py"
if (-not (Test-Path -LiteralPath $RemoteExec)) { throw "Missing $RemoteExec" }

$beforeText = if ($Before) { $Before.ToString("yyyy-MM-dd HH:mm:ss") } else { "" }
$afterText = if ($After) { $After.ToString("yyyy-MM-dd HH:mm:ss") } else { "" }
$targetText = ($Targets | Sort-Object -Unique) -join ","
$executeText = if ($Execute) { "1" } else { "0" }
$vacuumText = if ($VacuumAnalyze) { "1" } else { "0" }

$targetRows = @{
    raw5s = @(
        @{ Table = "bf_sensor.raw_5s_values"; Column = "ts" }
    )
    minute = @(
        @{ Table = "bf_sensor.one_minute_values"; Column = "ts" }
    )
    diagnosis = @(
        @{ Table = "bf_sensor.short_window_conversation_messages"; Column = "created_at" },
        @{ Table = "bf_sensor.conversation_delta_contexts"; Column = "created_at" },
        @{ Table = "bf_sensor.short_window_conversations"; Column = "updated_at" },
        @{ Table = "bf_sensor.short_window_summaries"; Column = "created_at" },
        @{ Table = "bf_sensor.diagnosis_queues"; Column = "queue_end_ts" },
        @{ Table = "bf_sensor.diagnosis_snapshots"; Column = "diagnosis_ts" }
    )
    quality = @(
        @{ Table = "bf_sensor.data_quality_status"; Column = "checked_at" }
    )
    automation = @(
        @{ Table = "bf_sensor.automation_runs"; Column = "started_at" },
        @{ Table = "bf_sensor.sync_runs"; Column = "started_at" }
    )
    zero_audit = @(
        @{ Table = "bf_sensor.zero_value_audits"; Column = "ts" }
    )
    backfill = @(
        @{ Table = "bf_sensor.backfill_tasks"; Column = "created_at" }
    )
}

$selectedRows = foreach ($target in ($Targets | Sort-Object -Unique)) {
    foreach ($item in $targetRows[$target]) {
        [PSCustomObject]@{
            target = $target
            table = $item.Table
            column = $item.Column
        }
    }
}
$targetsJson = ($selectedRows | ConvertTo-Json -Compress)
$targetsJsonEscaped = $targetsJson.Replace("'", "''")

$remoteScript = @"
`$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(`$false)
`$ErrorActionPreference = "Continue"
`$BeforeText = '$beforeText'
`$AfterText = '$afterText'
`$ExecuteDelete = '$executeText' -eq '1'
`$VacuumAnalyze = '$vacuumText' -eq '1'
`$TargetsJson = '$targetsJsonEscaped'

`$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath `$psql)) {
  Write-Host "PSQL_NOT_FOUND `$psql"
  exit 2
}

`$env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
if (-not `$env:PGPASSWORD) { `$env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "User") }
if (-not `$env:PGPASSWORD) { `$env:PGPASSWORD = `$env:GL02_PGPASSWORD }
`$pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
if (-not `$pgUser) { `$pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "User") }
if (-not `$pgUser) { `$pgUser = `$env:GL02_PGUSER }
if (-not `$pgUser) { `$pgUser = "gl02_sync" }

`$targets = `$TargetsJson | ConvertFrom-Json
if (`$targets -isnot [System.Array]) { `$targets = @(`$targets) }

Write-Host "===== CLEANUP PLAN ====="
[PSCustomObject]@{
  before = `$BeforeText
  after = `$AfterText
  execute = `$ExecuteDelete
  vacuum_analyze = `$VacuumAnalyze
  target_count = `$targets.Count
} | Format-List
`$targets | Format-Table -AutoSize

`$values = (`$targets | ForEach-Object {
  "('{0}','{1}','{2}')" -f (`$_.target -replace "'", "''"), (`$_.table -replace "'", "''"), (`$_.column -replace "'", "''")
}) -join ",`n"

`$mode = if (`$ExecuteDelete) { "EXECUTE_DELETE" } else { "DRY_RUN" }
`$sql = @"
\pset pager off
CREATE TEMP TABLE cleanup_targets(target text, table_name text, column_name text);
INSERT INTO cleanup_targets(target, table_name, column_name) VALUES
`$values;
CREATE TEMP TABLE cleanup_results(
  mode text,
  target text,
  table_name text,
  column_name text,
  rows_matched bigint,
  rows_deleted bigint,
  note text
);
DO `$do`$
DECLARE
  r record;
  before_ts timestamp := NULLIF('$beforeText', '')::timestamp;
  after_ts timestamp := NULLIF('$afterText', '')::timestamp;
  matched bigint := 0;
  deleted_count bigint := 0;
  rel regclass;
  condition_sql text;
BEGIN
  FOR r IN SELECT * FROM cleanup_targets LOOP
    rel := to_regclass(r.table_name);
    IF rel IS NULL THEN
      INSERT INTO cleanup_results VALUES ('$mode', r.target, r.table_name, r.column_name, 0, 0, 'missing_table');
      CONTINUE;
    END IF;
    condition_sql := 'true';
    IF before_ts IS NOT NULL THEN
      condition_sql := condition_sql || format(' AND %I < %L::timestamp', r.column_name, before_ts);
    END IF;
    IF after_ts IS NOT NULL THEN
      condition_sql := condition_sql || format(' AND %I >= %L::timestamp', r.column_name, after_ts);
    END IF;
    EXECUTE format('SELECT count(*) FROM %s WHERE %s', rel, condition_sql) INTO matched;
    IF '$executeText' = '1' THEN
      EXECUTE format('WITH deleted AS (DELETE FROM %s WHERE %s RETURNING 1) SELECT count(*) FROM deleted', rel, condition_sql) INTO deleted_count;
    ELSE
      deleted_count := 0;
    END IF;
    INSERT INTO cleanup_results VALUES ('$mode', r.target, r.table_name, r.column_name, matched, deleted_count, '');
  END LOOP;
END
`$do`$;
SELECT * FROM cleanup_results ORDER BY target, table_name;
"@

`$tmp = Join-Path `$env:TEMP ("bf_cleanup_{0}.sql" -f ([guid]::NewGuid().ToString("N")))
Set-Content -LiteralPath `$tmp -Value `$sql -Encoding UTF8
& `$psql -h 127.0.0.1 -p 5432 -U `$pgUser -d bf_trend -v ON_ERROR_STOP=1 -f `$tmp
`$exit = `$LASTEXITCODE
Remove-Item -LiteralPath `$tmp -Force -ErrorAction SilentlyContinue
if (`$exit -ne 0) { exit `$exit }

if (`$ExecuteDelete -and `$VacuumAnalyze) {
  Write-Host "===== VACUUM ANALYZE ====="
  foreach (`$target in `$targets) {
    `$table = [string]`$target.table
    `$exists = & `$psql -h 127.0.0.1 -p 5432 -U `$pgUser -d bf_trend -At -c "SELECT to_regclass('`$table') IS NOT NULL;"
    if (`$exists -match "t") {
      Write-Host ("VACUUM ANALYZE {0}" -f `$table)
      & `$psql -h 127.0.0.1 -p 5432 -U `$pgUser -d bf_trend -v ON_ERROR_STOP=0 -c "VACUUM (ANALYZE) `$table;"
    }
  }
}
"@

$tmpScript = Join-Path $env:TEMP ("cleanup_22012_pg_data_{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
Set-Content -LiteralPath $tmpScript -Value $remoteScript -Encoding UTF8
try {
    Write-Host "[cleanup] Running remote PostgreSQL cleanup plan. Execute=$Execute Targets=$targetText"
    & $Python $RemoteExec `
        --allow-agents-password `
        --workdir $RemoteRoot `
        --timeout 3600 `
        --script $tmpScript
    if ($LASTEXITCODE -ne 0) {
        throw "Remote cleanup failed with exit code $LASTEXITCODE"
    }
} finally {
    Remove-Item -LiteralPath $tmpScript -Force -ErrorAction SilentlyContinue
}
