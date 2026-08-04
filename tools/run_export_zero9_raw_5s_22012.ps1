param(
    [string]$StartTime = "2026-02-08 19:06:00",
    [string]$EndTime = "2026-05-14 14:19:00",
    [string]$OutputRoot = "",
    [int]$Retries = 10,
    [int]$RetrySleepSeconds = 60,
    [switch]$Overwrite
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $ProjectRoot "zero9_raw_5s_export"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ExportScript = Join-Path $ProjectRoot "tools\export_zero_9_raw_5s.py"
$StdoutLog = Join-Path $OutputRoot "export_raw_5s_stdout.log"
$StderrLog = Join-Path $OutputRoot "export_raw_5s_stderr.log"

Remove-Item -LiteralPath $StdoutLog, $StderrLog -ErrorAction SilentlyContinue

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$ArgsList = @(
    $ExportScript,
    "--start-time", $StartTime,
    "--end-time", $EndTime,
    "--output-root", $OutputRoot,
    "--retries", $Retries,
    "--retry-sleep-seconds", $RetrySleepSeconds
)

if ($Overwrite) {
    $ArgsList += "--overwrite"
}

& $PythonExe @ArgsList 1> $StdoutLog 2> $StderrLog
exit $LASTEXITCODE
