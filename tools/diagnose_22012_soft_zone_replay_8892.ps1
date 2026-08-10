$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python = 'C:\Program Files\Python311\python.exe'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$Server = Join-Path $StageRoot 'soft_zone_replay_server_20260808.py'
$DbConfig = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Stdout = Join-Path $StageRoot 'soft_zone_replay_8892_diag.stdout.log'
$Stderr = Join-Path $StageRoot 'soft_zone_replay_8892_diag.stderr.log'

Remove-Item -LiteralPath $Stdout -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Stderr -Force -ErrorAction SilentlyContinue

$arguments = @(
    '-u', $Server,
    '--host', '127.0.0.1',
    '--port', '8892',
    '--static-dir', $StageRoot,
    '--db-config', $DbConfig,
    '--log-level', 'INFO'
)

$process = Start-Process -FilePath $Python -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr
Start-Sleep -Seconds 5
$process.Refresh()

$health = $null
$healthError = $null
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8892/api/health' -TimeoutSec 10
}
catch {
    $healthError = $_.Exception.Message
}

$stdoutText = if (Test-Path -LiteralPath $Stdout) { @(Get-Content -LiteralPath $Stdout -Tail 80 | ForEach-Object { [string]$_ }) } else { @() }
$stderrText = if (Test-Path -LiteralPath $Stderr) { @(Get-Content -LiteralPath $Stderr -Tail 80 | ForEach-Object { [string]$_ }) } else { @() }

if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
}

[pscustomobject]@{
    pid = $process.Id
    exited = $process.HasExited
    exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
    health = $health
    health_error = $healthError
    stdout = $stdoutText
    stderr = $stderrText
} | ConvertTo-Json -Depth 6
