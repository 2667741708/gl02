$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
$LogPath = Join-Path $ScriptRoot ("logs\continuous_sync_pg_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    Write-Error "Please set GL02_PGUSER and GL02_PGPASSWORD first."
    exit 1
}

& $Python (Join-Path $ScriptRoot "src\sync_from_243_pg.py") `
    --continuous `
    --poll-seconds 30 `
    --lookback-minutes 10 `
    --chunk-hours 0.2 `
    --batch-size 115 `
    --max-workers 1 `
    --retries 3 `
    --retry-sleep 8 `
    --source-mode raw `
    --source-interval-seconds 5 `
    --source-aggregate average `
    --raw-max-values 20000 `
    --target-aggregate PS_RAW_AVERAGE `
    --target-interval-seconds 60 `
    --persist-raw-5s `
    --raw-retention-days 30 `
    *>&1 | Tee-Object -FilePath $LogPath
