$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$v3Root = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$v4Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stageRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Temp\bf_ws_handshake_fix_20260806'
$stage8770 = Join-Path $stageRoot 'pspace_8092_realtime_bridge.py'
$stage8768 = Join-Path $stageRoot 'local_pg_ws_bridge.py'
$target8770 = Join-Path $v3Root 'tools\pspace_8092_realtime_bridge.py'
$target8768 = Join-Path $v4Root '自动诊断服务\local_pg_ws_bridge.py'
$python = 'C:\Program Files\Python311\python.exe'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'V4BillboardPspace8770'
$serviceName = 'BFV4PreviewWs8768'

foreach ($path in @($stage8770, $stage8768, $target8770, $target8768, $python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required path: $path" }
}

& $python -m py_compile $stage8770 $stage8768
if ($LASTEXITCODE -ne 0) { throw 'Staged Python syntax validation failed' }

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$service = Get-Service -Name $serviceName -ErrorAction Stop
if ($task.State -ne 'Running') { throw "$taskName is not running before deployment" }
if ($service.Status -ne 'Running') { throw "$serviceName is not running before deployment" }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $v4Root "backups\ws_handshake_8768_8770_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $target8770 -Destination (Join-Path $backup 'pspace_8092_realtime_bridge.py') -Force
Copy-Item -LiteralPath $target8768 -Destination (Join-Path $backup 'local_pg_ws_bridge.py') -Force

$deployed = $false
try {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Stop-Service -Name $serviceName -Force
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 250
        $listen8768 = netstat -ano -p tcp | Select-String ':8768\s+.*LISTENING'
        $listen8770 = netstat -ano -p tcp | Select-String ':8770\s+.*LISTENING'
    } while (($listen8768 -or $listen8770) -and (Get-Date) -lt $deadline)
    # A blocked native pSpace/DB call may prevent graceful process exit.  Only
    # terminate a residual listener after its exact PID and command are proven.
    foreach ($entry in @(
        @{ Match = $listen8768; Port = 8768; Marker = 'local_pg_ws_bridge.py' },
        @{ Match = $listen8770; Port = 8770; Marker = 'pspace_8092_realtime_bridge.py' }
    )) {
        if (-not $entry.Match) { continue }
        $line = $entry.Match | Select-Object -First 1
        $oldPid = [int](($line.Line -split '\s+')[-1])
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$oldPid"
        if (-not $process -or $process.CommandLine -notlike "*$($entry.Marker)*") {
            throw "Refusing to terminate unverified listener on port $($entry.Port), PID $oldPid"
        }
        Stop-Process -Id $oldPid -Force
    }
    Start-Sleep -Seconds 1
    $listen8768 = netstat -ano -p tcp | Select-String ':8768\s+.*LISTENING'
    $listen8770 = netstat -ano -p tcp | Select-String ':8770\s+.*LISTENING'
    if ($listen8768 -or $listen8770) { throw 'Verified residual listener did not terminate' }

    Copy-Item -LiteralPath $stage8770 -Destination "$target8770.new" -Force
    Move-Item -LiteralPath "$target8770.new" -Destination $target8770 -Force
    Copy-Item -LiteralPath $stage8768 -Destination "$target8768.new" -Force
    Move-Item -LiteralPath "$target8768.new" -Destination $target8768 -Force
    $deployed = $true
}
finally {
    if (-not $deployed) {
        Copy-Item -LiteralPath (Join-Path $backup 'pspace_8092_realtime_bridge.py') -Destination $target8770 -Force
        Copy-Item -LiteralPath (Join-Path $backup 'local_pg_ws_bridge.py') -Destination $target8768 -Force
    }
    Start-Service -Name $serviceName
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
}

$deadline = (Get-Date).AddSeconds(60)
do {
    Start-Sleep -Milliseconds 500
    $listen8768 = netstat -ano -p tcp | Select-String ':8768\s+.*LISTENING'
    $listen8770 = netstat -ano -p tcp | Select-String ':8770\s+.*LISTENING'
    $service = Get-Service -Name $serviceName
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
} while ((-not $listen8768 -or -not $listen8770 -or $service.Status -ne 'Running' -or $task.State -ne 'Running') -and (Get-Date) -lt $deadline)

if (-not $listen8768 -or -not $listen8770) { throw '8768/8770 listeners did not recover' }
if ($service.Status -ne 'Running' -or $task.State -ne 'Running') { throw '8768/8770 managed runtime did not recover' }

[ordered]@{
    deployed = $deployed
    backup = $backup
    service8768 = $service.Status.ToString()
    task8770 = $task.State.ToString()
    listener8768 = ($listen8768.Line -join '; ')
    listener8770 = ($listen8770.Line -join '; ')
    sha8768 = (Get-FileHash -LiteralPath $target8768 -Algorithm SHA256).Hash
    sha8770 = (Get-FileHash -LiteralPath $target8770 -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 4
