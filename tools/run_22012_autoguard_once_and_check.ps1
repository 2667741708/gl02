$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V3"
$AutoDir = Join-Path $ProjectRoot "自动诊断服务"
$RunScript = Join-Path $AutoDir "run_auto_diagnosis_once.ps1"
if (-not (Test-Path -LiteralPath $RunScript)) {
    $AutoDir = Join-Path $ProjectRoot "auto_diagnosis_service"
    $RunScript = Join-Path $AutoDir "run_auto_diagnosis_once.ps1"
}
$LogDir = Join-Path $AutoDir "logs"
$TodayLog = Join-Path $LogDir ("auto_guard_once_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "OLLAMA_BASE_URL", "BF_LLM_MODEL") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://10.30.220.12:11434" }
if (-not $env:BF_LLM_MODEL) { $env:BF_LLM_MODEL = "chiqiong-blast-furnace:latest" }
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

"RUN_START`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
"PROJECT_ROOT`t$ProjectRoot"
"RUN_SCRIPT`t$RunScript"
"DB`t$($env:GL02_PGUSER)@$($env:GL02_PGHOST):$($env:GL02_PGPORT)/$($env:GL02_PGDATABASE)"
"OLLAMA`t$($env:OLLAMA_BASE_URL)`tMODEL=$($env:BF_LLM_MODEL)"

if (-not (Test-Path -LiteralPath $RunScript)) {
    "RUN_SCRIPT_MISSING`t$RunScript"
    exit 2
}

Set-Location -LiteralPath $ProjectRoot
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunScript
$exit = $LASTEXITCODE
"RUN_EXIT`t$exit"

if (Test-Path -LiteralPath $TodayLog) {
    "LOG_TAIL`t$TodayLog"
    Get-Content -LiteralPath $TodayLog -Tail 120 -Encoding UTF8
} else {
    "LOG_NOT_FOUND`t$TodayLog"
}

$psql = @("F:\PostgreSQL\16\bin\psql.exe", "C:\Program Files\PostgreSQL\16\bin\psql.exe", "psql.exe") |
    Where-Object { $_ -eq "psql.exe" -or (Test-Path -LiteralPath $_) } |
    Select-Object -First 1

if ($psql) {
    $sql = @"
WITH latest_sensor AS (
  SELECT max(ts) AS max_ts FROM bf_sensor.one_minute_values
),
latest_diag AS (
  SELECT * FROM bf_sensor.diagnosis_snapshots ORDER BY diagnosis_ts DESC, updated_at DESC LIMIT 1
),
latest_queue AS (
  SELECT * FROM bf_sensor.diagnosis_queues ORDER BY queue_end_ts DESC, updated_at DESC LIMIT 1
),
latest_summary AS (
  SELECT * FROM bf_sensor.short_window_summaries ORDER BY created_at DESC LIMIT 1
)
SELECT json_build_object(
  'db_now', localtimestamp::text,
  'sensor_max_ts', (SELECT max_ts::text FROM latest_sensor),
  'sensor_lag_min', (SELECT round(extract(epoch from (localtimestamp - max_ts))::numeric/60, 3) FROM latest_sensor),
  'diagnosis_ts', (SELECT diagnosis_ts::text FROM latest_diag),
  'diagnosis_lag_from_sensor_min', (SELECT round(extract(epoch from ((SELECT max_ts FROM latest_sensor) - diagnosis_ts))::numeric/60, 3) FROM latest_diag),
  'main_label', (SELECT main_label FROM latest_diag),
  'queue_id', (SELECT queue_id FROM latest_queue),
  'queue_end_ts', (SELECT queue_end_ts::text FROM latest_queue),
  'queue_count', (SELECT diagnosis_count FROM latest_queue),
  'queue_expected', (SELECT expected_count FROM latest_queue),
  'queue_status', (SELECT status FROM latest_queue),
  'summary_id', (SELECT summary_id FROM latest_summary),
  'summary_queue_id', (SELECT queue_id FROM latest_summary),
  'summary_created_at', (SELECT created_at::text FROM latest_summary),
  'summary_status', (SELECT status FROM latest_summary),
  'summary_chars', (SELECT length(llm_summary) FROM latest_summary),
  'summary_matches_latest_queue', (SELECT queue_id FROM latest_summary) = (SELECT queue_id FROM latest_queue)
)::text;
"@
    "DB_AFTER"
    & $psql -w -h $env:GL02_PGHOST -p $env:GL02_PGPORT -U $env:GL02_PGUSER -d $env:GL02_PGDATABASE -tA -c $sql
}

"RUN_END`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
exit $exit
