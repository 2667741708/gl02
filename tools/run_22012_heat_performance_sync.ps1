$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'HeatPerformanceQualitySync requires PowerShell 7 Core.'
}

$root = Split-Path -Parent $PSScriptRoot
$python = 'C:\Program Files\Python311\python.exe'
$script = Join-Path $root 'tools\sync_22012_heat_performance_quality.py'
$log = Join-Path $root 'logs\heat_performance_quality_sync.log'

foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
$env:PYTHONUTF8 = '1'

New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null
$runId = '{0}_{1}' -f (Get-Date -Format 'yyyyMMdd_HHmmss'), $PID
$stdoutPath = Join-Path (Split-Path -Parent $log) "heat_sync_$runId.stdout.tmp"
$stderrPath = Join-Path (Split-Path -Parent $log) "heat_sync_$runId.stderr.tmp"
$exitCode = 1
try {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value (
        "{`"event`":`"scheduled_sync_start`",`"run_id`":`"$runId`",`"started_at`":`"$((Get-Date).ToString('o'))`"}"
    )
    $process = Start-Process -FilePath $python -ArgumentList @(
        '-X', 'utf8', $script, '--source', 'local_mirror', '--since-days', '3'
    ) -WorkingDirectory $root -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $exitCode = [int]$process.ExitCode
    if (Test-Path -LiteralPath $stdoutPath) {
        Get-Content -LiteralPath $stdoutPath | Add-Content -LiteralPath $log -Encoding UTF8
    }
    if ((Test-Path -LiteralPath $stderrPath) -and (Get-Item -LiteralPath $stderrPath).Length -gt 0) {
        Get-Content -LiteralPath $stderrPath | Add-Content -LiteralPath $log -Encoding UTF8
    }
    Add-Content -LiteralPath $log -Encoding UTF8 -Value (
        "{`"event`":`"scheduled_sync_end`",`"run_id`":`"$runId`",`"exit_code`":$exitCode,`"finished_at`":`"$((Get-Date).ToString('o'))`"}"
    )
} catch {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value (
        "{`"event`":`"scheduled_sync_wrapper_error`",`"run_id`":`"$runId`",`"error_type`":`"$($_.Exception.GetType().Name)`"}"
    )
    $exitCode = 1
} finally {
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
}
exit $exitCode
