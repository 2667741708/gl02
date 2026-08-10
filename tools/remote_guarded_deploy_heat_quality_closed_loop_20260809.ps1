$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$taskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$syncTaskName = 'HeatPerformanceQualitySync'
$python = 'C:\Program Files\Python311\python.exe'
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\heat_quality_closed_loop_$stamp"
$syncLog = Join-Path $backupRoot 'manual_sync_output.log'

$files = @(
    [pscustomobject]@{
        Target = Join-Path $root '高炉前端数据\智能助手\backend\heat_performance_quality.py'
        Stage = Join-Path $stageRoot 'heat_performance_quality.closed_loop.py'
        Hash = 'F4555D9D0EC6D14314194C8CE78C8DD0E40A248CCFAF7F5BD4E19771CC875CAB'
        BackupName = 'root_heat_performance_quality.py.bak'
    },
    [pscustomobject]@{
        Target = Join-Path $standalone '高炉前端数据\智能助手\backend\heat_performance_quality.py'
        Stage = Join-Path $stageRoot 'heat_performance_quality.closed_loop.py'
        Hash = 'F4555D9D0EC6D14314194C8CE78C8DD0E40A248CCFAF7F5BD4E19771CC875CAB'
        BackupName = 'standalone_heat_performance_quality.py.bak'
    },
    [pscustomobject]@{
        Target = Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py'
        Stage = Join-Path $stageRoot 'sync_22012_heat_performance_quality.closed_loop.py'
        Hash = '30D8A8E8FB8508EFF6787DD76CB4AC005984412564FCC6EF44F9F4727489CABE'
        BackupName = 'standalone_sync_22012_heat_performance_quality.py.bak'
    }
)

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

function Wait-ServiceState([string]$Name, [string]$State, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name).Status.ToString() -eq $State) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $State"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening"
}

function Install-StagedFile($Item) {
    $temporary = "$($Item.Target).deploy_$stamp"
    Copy-Item -LiteralPath $Item.Stage -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Item.Target -Force
}

function Restore-Backups {
    foreach ($item in $files) {
        $backup = Join-Path $backupRoot $item.BackupName
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            Copy-Item -LiteralPath $backup -Destination $item.Target -Force
        }
    }
}

foreach ($required in @($root, $standalone, $manager, $configPath, $python)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required path: $required" }
}
foreach ($item in $files) {
    if (-not (Test-Path -LiteralPath $item.Stage -PathType Leaf)) {
        throw "Missing staged file: $($item.Stage)"
    }
    $actual = (Get-FileHash -LiteralPath $item.Stage -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "Staged hash mismatch: $($item.Stage)" }
}
& $python -m py_compile ($files | ForEach-Object { $_.Stage } | Select-Object -Unique)
if ($LASTEXITCODE -ne 0) { throw 'Staged Python compile failed' }

$protectedBefore = @{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedBefore[$port] = Get-ListenerPid $port
    if (-not $protectedBefore[$port]) { throw "Protected port $port is not listening" }
}
$listener8093Before = Get-ListenerPid 8093
$guardTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $guardTaskName -ErrorAction Stop
$syncTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $syncTaskName -ErrorAction Stop
$guardWasEnabled = $guardTask.State.ToString() -ne 'Disabled'
$syncWasEnabled = $syncTask.State.ToString() -ne 'Disabled'

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
foreach ($item in $files) {
    Copy-Item -LiteralPath $item.Target -Destination (Join-Path $backupRoot $item.BackupName) -Force
}

$serviceStopped = $false
$deployed = $false
$rollbackApplied = $false
$syncFinal = $null
try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $syncTaskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $syncTaskName -ErrorAction SilentlyContinue
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $guardTaskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $guardTaskName -ErrorAction SilentlyContinue

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Stopped'
    Wait-Port 8093 $false
    $serviceStopped = $true

    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[$port]) {
            throw "Protected PID changed before deployment on port $port"
        }
    }
    foreach ($item in $files) { Install-StagedFile $item }
    $deployed = $true

    & $python -m py_compile ($files | ForEach-Object { $_.Target })
    if ($LASTEXITCODE -ne 0) { throw 'Deployed Python compile failed' }

    foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
        if ($value) { Set-Item -Path "Env:$name" -Value $value }
    }
    $env:PYTHONUTF8 = '1'
    Push-Location -LiteralPath $standalone
    try {
        $syncOutput = @(& $python -X utf8 '.\tools\sync_22012_heat_performance_quality.py' --source local_mirror --since-days 3 --repair-days 3 --repair-max-rows 5000 2>&1)
        $syncExitCode = $LASTEXITCODE
        $syncOutput | Set-Content -LiteralPath $syncLog -Encoding UTF8
        if ($syncExitCode -ne 0) { throw "Manual local-mirror sync failed; see $syncLog" }
        if ($syncOutput.Count -gt 0) {
            $syncFinal = $syncOutput[$syncOutput.Count - 1].ToString() | ConvertFrom-Json
        }
    } finally {
        Pop-Location
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    $serviceStopped = $false

    $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=$stamp" -TimeoutSec 30
    if ([int]$page.StatusCode -ne 200) { throw '8093 page did not return HTTP 200' }
    $api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/heat-performance-quality?limit=5&t=$stamp" -TimeoutSec 30
    if (-not $api.ok -or @($api.items).Count -lt 1) { throw '8093 heat-performance API returned no facts' }
    $heat089 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-089&limit=5&include_future=1' -TimeoutSec 30
    $heat090 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-090&limit=5&include_future=1' -TimeoutSec 30
    if (-not $heat089.ok -or @($heat089.items).Count -lt 1) { throw 'Heat 089 verification failed' }
    if (-not $heat090.ok -or @($heat090.items).Count -lt 1) { throw 'Heat 090 verification failed' }
} catch {
    $deployError = $_
    try {
        if ((Get-Service -Name $serviceName).Status.ToString() -ne 'Stopped') {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
            Wait-ServiceState $serviceName 'Stopped'
            Wait-Port 8093 $false
        }
        Restore-Backups
        $rollbackApplied = $true
    } catch {
        Write-Warning "File rollback failed: $($_.Exception.Message)"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    throw $deployError
} finally {
    if ($syncWasEnabled) {
        Enable-ScheduledTask -TaskPath $taskPath -TaskName $syncTaskName -ErrorAction SilentlyContinue | Out-Null
    }
    if ($guardWasEnabled) {
        Enable-ScheduledTask -TaskPath $taskPath -TaskName $guardTaskName -ErrorAction SilentlyContinue | Out-Null
    }
}

$protectedAfter = @{}
foreach ($port in @(8768, 8094, 8770)) {
    $protectedAfter[$port] = Get-ListenerPid $port
    if ($protectedAfter[$port] -ne $protectedBefore[$port]) {
        throw "Protected PID changed after deployment on port $port"
    }
}
foreach ($item in $files) {
    $actual = (Get-FileHash -LiteralPath $item.Target -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "Deployed hash mismatch: $($item.Target)" }
}

$finalApi = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?limit=5' -TimeoutSec 30
$final089 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-089&limit=5&include_future=1' -TimeoutSec 30
$final090 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-090&limit=5&include_future=1' -TimeoutSec 30

[ordered]@{
    schema = 'ops.8093.heat-quality-closed-loop.v2'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    sync_log = $syncLog
    listener_8093_before = $listener8093Before
    listener_8093_after = Get-ListenerPid 8093
    guard_restored = (Get-ScheduledTask -TaskPath $taskPath -TaskName $guardTaskName).State.ToString() -ne 'Disabled'
    sync_task_restored = (Get-ScheduledTask -TaskPath $taskPath -TaskName $syncTaskName).State.ToString() -ne 'Disabled'
    sync_result = $syncFinal
    api_count = @($finalApi.items).Count
    heat_089 = @($final089.items)[0]
    heat_090 = @($final090.items)[0]
    rollback_applied = $rollbackApplied
    protected_pids = [ordered]@{
        port_8768_before = $protectedBefore[8768]; port_8768_after = $protectedAfter[8768]
        port_8094_before = $protectedBefore[8094]; port_8094_after = $protectedAfter[8094]
        port_8770_before = $protectedBefore[8770]; port_8770_after = $protectedAfter[8770]
    }
    deployed_hashes = [ordered]@{
        heat_performance_quality = $files[0].Hash
        sync_22012_heat_performance_quality = $files[2].Hash
    }
} | ConvertTo-Json -Depth 12
