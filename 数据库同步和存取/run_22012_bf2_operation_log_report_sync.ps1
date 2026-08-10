$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
$SyncScript = Join-Path $ScriptRoot "sync_bf2_operation_log_report.py"
$LogDir = Join-Path $ScriptRoot "logs"
$null = New-Item -ItemType Directory -Force -Path $LogDir
$LogPath = Join-Path $LogDir ("bf2_operation_log_report_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not (Test-Path -LiteralPath $SyncScript)) {
    throw "Cannot find report sync script: $SyncScript"
}

$ReportBaseUrl = if ($env:IMES_REPORT_BASE_URL) { $env:IMES_REPORT_BASE_URL } else { "http://127.0.0.1:18084/" }

& $Python $SyncScript `
    --date (Get-Date -Format "yyyy-MM-dd") `
    --report-base-url $ReportBaseUrl `
    --max-rows 0 *>&1 | Tee-Object -FilePath $LogPath

if ($LASTEXITCODE -ne 0) {
    throw "bf2 operation-log report sync failed with exit code $LASTEXITCODE"
}
