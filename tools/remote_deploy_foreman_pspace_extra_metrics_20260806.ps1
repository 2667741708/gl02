$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$v3Root = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$v4Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Temp\foreman_pspace_extra_20260806'
$stageBridge = Join-Path $stage 'pspace_8092_realtime_bridge.py'
$stageJs = Join-Path $stage 'foreman-trend-preview.js'
$stageCoalMath = Join-Path $stage 'foreman-coal-math.js'
$stageHtml = Join-Path $stage 'foreman_trend_preview.html'
$targetBridge = Join-Path $v3Root 'tools\pspace_8092_realtime_bridge.py'
$targetJs = Join-Path $v4Root '高炉前端数据\assets\foreman-trend-preview.js'
$targetCoalMath = Join-Path $v4Root '高炉前端数据\assets\foreman-coal-math.js'
$targetHtml = Join-Path $v4Root '高炉前端数据\foreman_trend_preview.html'
$python = 'C:\Program Files\Python311\python.exe'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'V4BillboardPspace8770'

function Get-ListenerPid([int]$Port) {
    foreach ($line in @(netstat -ano -p tcp)) {
        if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            return [int]$Matches[1]
        }
    }
    return $null
}

foreach ($path in @($stageBridge, $stageJs, $stageCoalMath, $stageHtml, $targetBridge, $targetJs, $targetHtml, $python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required path: $path" }
}
& $python -m py_compile $stageBridge
if ($LASTEXITCODE -ne 0) { throw 'Staged bridge syntax validation failed' }
$bridgeText = Get-Content -LiteralPath $stageBridge -Raw -Encoding UTF8
$jsText = Get-Content -LiteralPath $stageJs -Raw -Encoding UTF8
$coalMathText = Get-Content -LiteralPath $stageCoalMath -Raw -Encoding UTF8
$htmlText = Get-Content -LiteralPath $stageHtml -Raw -Encoding UTF8
foreach ($marker in @(
    'FOREMAN_EXTRA_SENSORS', 'SIO_GL02_PC_T0004', 'SIO_GL02_BT_T0136',
    'SIO_GL02_BT_T0133', 'SIO_GL02_BT_T0134', 'SIO_GL02_BT_T0056',
    'SIO_GL02_BT_T0137', 'SIO_GL02_BT_T0021', 'SIO_GL02_BT_T0148',
    'SIO_GL02_BT_T0147', 'SIO_GL02_BT_T0097', 'SIO_GL02_LD_T0059',
    'SIO_GL02_LD_T0045', 'SIO_GL02_LD_T0073', 'SIO_GL02_CX_T0289',
    'SIO_GL02_CX_T0291', 'SIO_CC_GF2_T0111', 'SIO_CC_GF2_T0112',
    'SIO_CC_GF2_T0113'
)) {
    if (-not $bridgeText.Contains($marker)) { throw "Bridge marker missing: $marker" }
}
if (-not $jsText.Contains("value === null || value === undefined || value === ''")) { throw 'Missing-value marker absent' }
if (-not $coalMathText.Contains('integrateRateSeries')) { throw 'Timestamp-aware coal integration marker absent' }
if (-not $htmlText.Contains('20260806-pspace-extra-r3')) { throw 'HTML cache marker absent' }

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State -ne 'Running') { throw "$taskName is not running before deployment" }
if ((Get-Service BFV4PreviewWs8768).Status -ne 'Running') { throw 'BFV4PreviewWs8768 is not running' }
$pid8768 = Get-ListenerPid 8768
$pid8093 = Get-ListenerPid 8093
$pid8094 = Get-ListenerPid 8094
if (-not $pid8768 -or -not $pid8093 -or -not $pid8094) { throw 'Protected listener missing before deployment' }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $v4Root "backups\foreman_pspace_extra_20260806\$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetBridge -Destination (Join-Path $backup 'pspace_8092_realtime_bridge.py') -Force
Copy-Item -LiteralPath $targetJs -Destination (Join-Path $backup 'foreman-trend-preview.js') -Force
if (Test-Path -LiteralPath $targetCoalMath) {
    Copy-Item -LiteralPath $targetCoalMath -Destination (Join-Path $backup 'foreman-coal-math.js') -Force
}
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backup 'foreman_trend_preview.html') -Force

$deployed = $false
try {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    $stopDeadline = (Get-Date).AddSeconds(35)
    do {
        $oldPid = Get-ListenerPid 8770
        if (-not $oldPid) { break }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$oldPid"
        if (-not $process -or $process.CommandLine -notlike '*pspace_8092_realtime_bridge.py*') {
            throw "Refusing to terminate unverified 8770 PID $oldPid"
        }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
        if ($parent -and $parent.CommandLine -like '*run_billboard_pspace_8770.py*') {
            Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 750
    } while ((Get-Date) -lt $stopDeadline)
    if (Get-ListenerPid 8770) { throw 'Old 8770 listener did not stop after verified process-tree termination' }

    foreach ($item in @(
        @{ Source = $stageBridge; Target = $targetBridge },
        @{ Source = $stageJs; Target = $targetJs },
        @{ Source = $stageCoalMath; Target = $targetCoalMath },
        @{ Source = $stageHtml; Target = $targetHtml }
    )) {
        $newPath = "$($item.Target).new"
        Copy-Item -LiteralPath $item.Source -Destination $newPath -Force
        Move-Item -LiteralPath $newPath -Destination $item.Target -Force
    }
    $deployed = $true
}
finally {
    if (-not $deployed) {
        Copy-Item -LiteralPath (Join-Path $backup 'pspace_8092_realtime_bridge.py') -Destination $targetBridge -Force
        Copy-Item -LiteralPath (Join-Path $backup 'foreman-trend-preview.js') -Destination $targetJs -Force
        $backupCoalMath = Join-Path $backup 'foreman-coal-math.js'
        if (Test-Path -LiteralPath $backupCoalMath) {
            Copy-Item -LiteralPath $backupCoalMath -Destination $targetCoalMath -Force
        }
        elseif (Test-Path -LiteralPath $targetCoalMath) {
            Remove-Item -LiteralPath $targetCoalMath -Force
        }
        Copy-Item -LiteralPath (Join-Path $backup 'foreman_trend_preview.html') -Destination $targetHtml -Force
    }
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
}

$deadline = (Get-Date).AddSeconds(60)
do {
    Start-Sleep -Milliseconds 500
    $pid8770 = Get-ListenerPid 8770
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
} while ((-not $pid8770 -or $task.State -ne 'Running') -and (Get-Date) -lt $deadline)
if (-not $pid8770 -or $task.State -ne 'Running') { throw 'Existing 8770 task did not recover' }
if ((Get-ListenerPid 8768) -ne $pid8768) { throw 'Protected 8768 PID changed' }
if ((Get-ListenerPid 8093) -ne $pid8093) { throw 'Protected 8093 PID changed' }
if ((Get-ListenerPid 8094) -ne $pid8094) { throw 'Protected 8094 PID changed' }
$response = Invoke-WebRequest -Uri 'http://127.0.0.1:8093/foreman_trend_preview.html?verify=pspace-extra-r3' -UseBasicParsing -TimeoutSec 20
if ($response.StatusCode -ne 200 -or $response.Content -notlike '*20260806-pspace-extra-r3*') { throw '8093 page verification failed' }
$coalResponse = Invoke-WebRequest -Uri 'http://127.0.0.1:8093/assets/foreman-coal-math.js?verify=coal-hour-r1' -UseBasicParsing -TimeoutSec 20
if ($coalResponse.StatusCode -ne 200 -or $coalResponse.Content -notlike '*integrateRateSeries*') { throw '8093 coal integration asset verification failed' }

[ordered]@{
    deployed = $deployed
    backup = $backup
    pid8770 = $pid8770
    pid8768_unchanged = $pid8768
    pid8093_unchanged = $pid8093
    pid8094_unchanged = $pid8094
    http8093 = $response.StatusCode
    bridge_sha256 = (Get-FileHash -LiteralPath $targetBridge -Algorithm SHA256).Hash
    js_sha256 = (Get-FileHash -LiteralPath $targetJs -Algorithm SHA256).Hash
    coal_math_sha256 = (Get-FileHash -LiteralPath $targetCoalMath -Algorithm SHA256).Hash
    html_sha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 4
