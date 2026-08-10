$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$python = 'C:\Program Files\Python311\python.exe'
$script = 'C:\Users\Administrator\AppData\Local\Temp\replay_abc33_rules.candidate.py'
$output = 'C:\Users\Administrator\AppData\Local\Temp\abc33_three_day_shadow_replay_c_gate.json'
$env:ABC33_SERVICE_ROOT = Join-Path $root '自动诊断服务'
$env:ABC33_PATCH_ROOT = 'C:\Users\Administrator\AppData\Local\Temp\abc33-c-event-patch'

foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}
if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = '127.0.0.1' }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = '5432' }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = 'bf_trend' }
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }
if (-not (Test-Path -LiteralPath $script)) { throw "replay script missing: $script" }

& $python -X utf8 $script --days 3 --step-minutes 5 --evaluate-rules-shadow --output $output
if ($LASTEXITCODE -ne 0) { throw "ABC33 three-day shadow replay failed: $LASTEXITCODE" }

$target = $output
if (-not (Test-Path -LiteralPath $target)) { throw "replay output missing: $target" }
Get-Content -LiteralPath $target -Raw -Encoding UTF8 | ConvertFrom-Json | Select-Object schema_version,window_start,window_end,attempted_batches,successful_batches,error_counts,production_scores_opened,production_alerts_opened | ConvertTo-Json -Depth 6
