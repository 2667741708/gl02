$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

$ProjectRoot = "F:\高炉炼铁项目-real-sensor-v2_V3"
$AutoDir = Join-Path $ProjectRoot "auto_diagnosis_service"
$Script = Join-Path $AutoDir "llm_short_window_summarizer.py"
$Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
if (-not $Python) { $Python = "C:\Program Files\Python311\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "OLLAMA_BASE_URL", "BF_LLM_MODEL") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://10.30.220.12:11434" }
if (-not $env:BF_LLM_MODEL) { $env:BF_LLM_MODEL = "chiqiong-blast-furnace:latest" }
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

"SUMMARY_RUN_START`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
"SCRIPT`t$Script"
"DB`t$($env:GL02_PGUSER)@$($env:GL02_PGHOST):$($env:GL02_PGPORT)/$($env:GL02_PGDATABASE)"
"OLLAMA`t$($env:OLLAMA_BASE_URL)`tMODEL=$($env:BF_LLM_MODEL)"

Set-Location -LiteralPath $ProjectRoot
& $Python -X utf8 $Script --latest --write --export-docx --model $env:BF_LLM_MODEL --ollama-url $env:OLLAMA_BASE_URL
$exit = $LASTEXITCODE
"SUMMARY_RUN_EXIT`t$exit"

$psql = @("F:\PostgreSQL\16\bin\psql.exe", "C:\Program Files\PostgreSQL\16\bin\psql.exe", "psql.exe") |
    Where-Object { $_ -eq "psql.exe" -or (Test-Path -LiteralPath $_) } |
    Select-Object -First 1

if ($psql) {
    $sql = @"
SELECT json_build_object(
  'queue', (
    SELECT json_build_object(
      'queue_id', queue_id,
      'queue_end_ts', queue_end_ts::text,
      'diagnosis_count', diagnosis_count,
      'expected_count', expected_count,
      'status', status
    )
    FROM bf_sensor.diagnosis_queues
    ORDER BY queue_end_ts DESC, updated_at DESC
    LIMIT 1
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
      'summary_head', left(regexp_replace(llm_summary, '\s+', ' ', 'g'), 400)
    )
    FROM bf_sensor.short_window_summaries
    ORDER BY created_at DESC
    LIMIT 1
  )
)::text;
"@
    "SUMMARY_DB_AFTER"
    & $psql -w -h $env:GL02_PGHOST -p $env:GL02_PGPORT -U $env:GL02_PGUSER -d $env:GL02_PGDATABASE -tA -c $sql
}

"SUMMARY_RUN_END`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
exit $exit
