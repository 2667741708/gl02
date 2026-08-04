$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

function Load-MachineEnv {
    foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "OLLAMA_BASE_URL", "BF_LLM_MODEL") {
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
}

function Find-Psql {
    $candidates = @(
        "F:\PostgreSQL\16\bin\psql.exe",
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "psql.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -eq "psql.exe") { return $candidate }
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Invoke-QueryJson {
    param(
        [string]$Sql
    )
    if (-not $script:Psql) {
        return @{ ok = $false; error = "psql not found" }
    }
    if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
        return @{ ok = $false; error = "missing GL02_PGUSER/GL02_PGPASSWORD" }
    }
    $raw = & $script:Psql -w `
        -h $env:GL02_PGHOST `
        -p $env:GL02_PGPORT `
        -U $env:GL02_PGUSER `
        -d $env:GL02_PGDATABASE `
        -tA `
        -c $Sql 2>&1
    if ($LASTEXITCODE -ne 0) {
        return @{ ok = $false; error = ($raw -join "`n") }
    }
    $text = ($raw -join "`n").Trim()
    try {
        return @{ ok = $true; data = ($text | ConvertFrom-Json) }
    } catch {
        return @{ ok = $false; error = "json parse failed"; raw = $text }
    }
}

function Test-HttpJson {
    param(
        [string]$Url,
        [int]$TimeoutSec = 8
    )
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSec
        $body = $resp.Content
        $parsed = $null
        try { $parsed = $body | ConvertFrom-Json } catch { $parsed = $body }
        return @{ ok = $true; status = [int]$resp.StatusCode; body = $parsed }
    } catch {
        return @{ ok = $false; error = $_.Exception.Message }
    }
}

Load-MachineEnv
$script:Psql = Find-Psql

$tasks = @()
foreach ($pair in @(
    @{ Path = "\GL02SensorSync\"; Name = "Watchdog" },
    @{ Path = "\GL02AutoDiagnosis\"; Name = "RunOnce" },
    @{ Path = "\GL02SensorSync\"; Name = "Realtime" },
    @{ Path = "\GL02SensorSync\"; Name = "History90d" },
    @{ Path = "\BlastFurnaceServices\"; Name = "BaselineProxy8092" }
)) {
    try {
        $task = Get-ScheduledTask -TaskPath $pair.Path -TaskName $pair.Name -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskPath $pair.Path -TaskName $pair.Name -ErrorAction Stop
        $tasks += [pscustomobject]@{
            task = "$($pair.Path)$($pair.Name)"
            state = $task.State.ToString()
            last_result = $info.LastTaskResult
            last_run = $info.LastRunTime
            next_run = $info.NextRunTime
        }
    } catch {
        $tasks += [pscustomobject]@{
            task = "$($pair.Path)$($pair.Name)"
            state = "missing"
            last_result = $null
            last_run = $null
            next_run = $null
        }
    }
}

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match "run_realtime_sync_pg_bg.ps1" -or
            $_.CommandLine -match "sync_from_243_pg.py" -or
            $_.CommandLine -match "sync_watchdog.py" -or
            $_.CommandLine -match "auto_guard_once.py" -or
            $_.CommandLine -match "ollama_proxy_server.py" -or
            $_.CommandLine -match "ollama"
        )
    } |
    Select-Object ProcessId, Name, CreationDate, CommandLine

$ports = foreach ($port in 5432, 8092, 8767, 11434, 8777) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    [pscustomobject]@{
        port = $port
        listening = [bool]$listeners
        owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    }
}

$sql = @"
WITH latest_sensor AS (
  SELECT max(ts) AS max_ts FROM bf_sensor.one_minute_values
),
tag_count AS (
  SELECT count(DISTINCT tag_long_name) AS tags_latest_10m
  FROM bf_sensor.one_minute_values
  WHERE ts >= (SELECT max_ts - interval '10 minutes' FROM latest_sensor)
),
latest_diag AS (
  SELECT *
  FROM bf_sensor.diagnosis_snapshots
  ORDER BY diagnosis_ts DESC, updated_at DESC
  LIMIT 1
),
latest_queue AS (
  SELECT *
  FROM bf_sensor.diagnosis_queues
  ORDER BY queue_end_ts DESC, updated_at DESC
  LIMIT 1
),
latest_summary AS (
  SELECT s.*
  FROM bf_sensor.short_window_summaries s
  ORDER BY s.created_at DESC
  LIMIT 1
),
latest_quality AS (
  SELECT *
  FROM bf_sensor.data_quality_status
  ORDER BY checked_at DESC
  LIMIT 1
),
latest_run AS (
  SELECT *
  FROM bf_sensor.automation_runs
  ORDER BY started_at DESC
  LIMIT 1
)
SELECT json_build_object(
  'db_now', localtimestamp::text,
  'connection', json_build_object(
    'host', inet_server_addr()::text,
    'port', inet_server_port(),
    'database', current_database(),
    'user', current_user
  ),
  'sensor', json_build_object(
    'max_ts', (SELECT max_ts::text FROM latest_sensor),
    'lag_min', (SELECT round(extract(epoch from (localtimestamp - max_ts))::numeric/60, 3) FROM latest_sensor),
    'tags_latest_10m', (SELECT tags_latest_10m FROM tag_count)
  ),
  'diagnosis', (
    SELECT json_build_object(
      'diagnosis_ts', diagnosis_ts::text,
      'updated_at', updated_at::text,
      'lag_from_sensor_min', (SELECT round(extract(epoch from ((SELECT max_ts FROM latest_sensor) - diagnosis_ts))::numeric/60, 3)),
      'lag_from_db_now_min', round(extract(epoch from (localtimestamp - diagnosis_ts))::numeric/60, 3),
      'main_label', main_label,
      'main_score', main_score,
      'main_confidence', main_confidence,
      'secondary_label', secondary_label,
      'source', source,
      'data_coverage', data_coverage,
      'missing_count', jsonb_array_length(COALESCE(missing_variables, '[]'::jsonb))
    ) FROM latest_diag
  ),
  'queue', (
    SELECT json_build_object(
      'queue_id', queue_id,
      'queue_start_ts', queue_start_ts::text,
      'queue_end_ts', queue_end_ts::text,
      'updated_at', updated_at::text,
      'diagnosis_count', diagnosis_count,
      'expected_count', expected_count,
      'status', status,
      'lag_from_diagnosis_min', (SELECT round(extract(epoch from ((SELECT diagnosis_ts FROM latest_diag) - queue_end_ts))::numeric/60, 3)),
      'lag_from_sensor_min', (SELECT round(extract(epoch from ((SELECT max_ts FROM latest_sensor) - queue_end_ts))::numeric/60, 3))
    ) FROM latest_queue
  ),
  'summary', (
    SELECT json_build_object(
      'summary_id', summary_id,
      'queue_id', queue_id,
      'created_at', created_at::text,
      'updated_at', updated_at::text,
      'model_name', model_name,
      'status', status,
      'summary_chars', length(llm_summary),
      'summary_head', left(regexp_replace(llm_summary, '\s+', ' ', 'g'), 240),
      'queue_matches_latest', queue_id = (SELECT queue_id FROM latest_queue)
    ) FROM latest_summary
  ),
  'quality', (
    SELECT json_build_object(
      'checked_at', checked_at::text,
      'window_kind', window_kind,
      'window_end', window_end::text,
      'latest_data_ts', latest_data_ts::text,
      'status', status,
      'coverage_ratio', coverage_ratio,
      'missing_count', jsonb_array_length(COALESCE(missing_variables, '[]'::jsonb))
    ) FROM latest_quality
  ),
  'latest_automation_run', (
    SELECT json_build_object(
      'task_name', task_name,
      'started_at', started_at::text,
      'finished_at', finished_at::text,
      'status', status,
      'window_end', window_end::text,
      'message', left(message, 240),
      'details', details
    ) FROM latest_run
  ),
  'counts', json_build_object(
    'diagnosis_snapshots', (SELECT count(*) FROM bf_sensor.diagnosis_snapshots),
    'diagnosis_queues', (SELECT count(*) FROM bf_sensor.diagnosis_queues),
    'short_window_summaries', (SELECT count(*) FROM bf_sensor.short_window_summaries),
    'data_quality_status', (SELECT count(*) FROM bf_sensor.data_quality_status)
  )
)::text;
"@

$dbHealth = Invoke-QueryJson -Sql $sql
$ollamaVersion = Test-HttpJson -Url "http://127.0.0.1:11434/api/version"
$proxyStatus = Test-HttpJson -Url "http://127.0.0.1:8092/api/ollama/status"
$shortWindow = Test-HttpJson -Url "http://127.0.0.1:8092/api/short-window/conversations?limit=1"

[pscustomobject]@{
    checked_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    db_env = [pscustomobject]@{
        host = $env:GL02_PGHOST
        port = $env:GL02_PGPORT
        database = $env:GL02_PGDATABASE
        user = $env:GL02_PGUSER
        password_set = [bool]$env:GL02_PGPASSWORD
        ollama_base_url = $env:OLLAMA_BASE_URL
        model = $env:BF_LLM_MODEL
    }
    psql = $script:Psql
    tasks = $tasks
    ports = $ports
    processes = $processes
    db_health = $dbHealth
    ollama_version = $ollamaVersion
    proxy_status = $proxyStatus
    short_window_api = $shortWindow
} | ConvertTo-Json -Depth 12
