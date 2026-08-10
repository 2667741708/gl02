$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$python = 'C:\Program Files\Python311\python.exe'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$tempRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$uploadedSync = Join-Path $tempRoot 'sync_22012_heat_performance_quality.py'
$uploadedRunner = Join-Path $tempRoot 'run_22012_heat_performance_sync.ps1'
$targetSync = Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py'
$targetRunner = Join-Path $standalone 'tools\run_22012_heat_performance_sync.ps1'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\local_imes_heat_recovery_20260808\$stamp"

function Install-AtomicFile {
    param([string]$Source, [string]$Target)
    $temporary = "$Target.local_imes_installing"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Get-RecoveredHeat {
    param([string]$Meltno = '2#20260808-110')
    $last = $null
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        try {
            $encoded = [Uri]::EscapeDataString($Meltno)
            return Invoke-RestMethod -Uri ("http://127.0.0.1:8093/api/si-v20/history?meltno=$encoded&limit=2") -TimeoutSec 30
        }
        catch {
            $last = $_
            Start-Sleep -Seconds 2
        }
    }
    throw $last
}

foreach ($path in @($python, $uploadedSync, $uploadedRunner, $targetSync, $targetRunner)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "required file missing: $path"
    }
}

& $python -X utf8 -m py_compile $uploadedSync
if ($LASTEXITCODE -ne 0) { throw 'staged local mirror sync syntax check failed' }
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $uploadedRunner, [ref]$null, [ref]$parseErrors
)
if ($parseErrors) { throw "staged runner syntax check failed: $parseErrors" }

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$wasEnabled = [bool]$task.Settings.Enabled
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetSync -Destination (Join-Path $backup 'sync_22012_heat_performance_quality.py') -Force
Copy-Item -LiteralPath $targetRunner -Destination (Join-Path $backup 'run_22012_heat_performance_sync.ps1') -Force

$installed = $false
$taskRestored = $false
try {
    if ($wasEnabled) { Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null }
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Install-AtomicFile -Source $uploadedSync -Target $targetSync
    Install-AtomicFile -Source $uploadedRunner -Target $targetRunner
    $installed = $true

    foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
        if ($value) { Set-Item -Path "Env:$name" -Value $value }
    }
    $ErrorActionPreference = 'Continue'
    $syncOutput = & $python -X utf8 $targetSync --source local_mirror --since-days 3 2>&1
    $syncExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($syncExitCode -ne 0) { throw "local mirror recovery run failed: $syncOutput" }
    $api = Get-RecoveredHeat -Meltno '2#20260808-110'
    $heat110 = $api.items | Where-Object { $_.target_meltno -eq '2#20260808-110' -and $null -ne $_.actual_si_mean } | Select-Object -First 1
    if (-not $heat110) { throw 'recovered heat 2#20260808-110 is still absent from summary API' }
    if ([math]::Abs([double]$heat110.actual_si_mean - 0.41) -gt 0.005) {
        throw "recovered heat 110 Si mismatch: $($heat110.actual_si_mean)"
    }
    $api112 = Get-RecoveredHeat -Meltno '2#20260808-112'
    $heat112 = $api112.items | Where-Object { $_.target_meltno -eq '2#20260808-112' -and $null -ne $_.actual_si_mean } | Select-Object -First 1
    if (-not $heat112) { throw 'recovered heat 2#20260808-112 is still absent from summary API' }
    if ([math]::Abs([double]$heat112.actual_si_mean - 0.53) -gt 0.005) {
        throw "recovered heat 112 Si mismatch: $($heat112.actual_si_mean)"
    }
}
catch {
    Install-AtomicFile -Source (Join-Path $backup 'sync_22012_heat_performance_quality.py') -Target $targetSync
    Install-AtomicFile -Source (Join-Path $backup 'run_22012_heat_performance_sync.ps1') -Target $targetRunner
    throw
}
finally {
    if ($wasEnabled) {
        Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    }
    $taskRestored = ((Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).Settings.Enabled -eq $wasEnabled)
}

[ordered]@{
    schema = 'ops.local-imes-heat-recovery.deploy.v1'
    deployed_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    backup = $backup
    installed = $installed
    source = 'bf_imes.raw_rows on 220.12'
    external_imes_called = $false
    task_enabled_restored = $taskRestored
    recovered_meltno = $heat110.target_meltno
    recovered_open_ts = $heat110.target_open_ts
    recovered_si_avg = $heat110.actual_si_mean
    recovered_112_si_avg = $heat112.actual_si_mean
    sync_output = @($syncOutput)
} | ConvertTo-Json -Depth 6
