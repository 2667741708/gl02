$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
$LogPath = Join-Path $ScriptRoot ("logs\history_sync_90d_pg_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    Write-Error "Please set GL02_PGUSER and GL02_PGPASSWORD first."
    exit 1
}

& $Python (Join-Path $ScriptRoot "src\sync_from_243_pg.py") `
    --days 90 `
    --chunk-hours 12 `
    --batch-size 8 `
    --max-workers 2 `
    --retries 3 `
    --retry-sleep 8 `
    --source-mode processed `
    *>&1 | Tee-Object -FilePath $LogPath
