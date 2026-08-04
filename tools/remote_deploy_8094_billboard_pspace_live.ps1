$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$v3Root = "F:\高炉炼铁项目-real-sensor-v2_V3"
$v4Root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$stageRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Temp\bf3d_billboard_pspace_live"
$stageBridge = Join-Path $stageRoot "pspace_8092_realtime_bridge.py"
$stageLauncher = Join-Path $stageRoot "run_billboard_pspace_8770.py"
$stageAdapter = Join-Path $stageRoot "bf3d-furnace-body-billboard-adapter.js"
$targetBridge = Join-Path $v3Root "tools\pspace_8092_realtime_bridge.py"
$targetLauncher = Join-Path $v3Root "tools\run_billboard_pspace_8770.py"
$targetAdapter = Join-Path $v4Root "高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js"
$targetHtml = Join-Path $v4Root "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$credentialSample = Join-Path $v3Root "pythonSDK(1)\read_sensor_data.py"
$sdkModule = Join-Path $v3Root "pythonSDK(1)\PythonAPI\PsServer.py"
$python = "C:\Program Files\Python311\python.exe"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V4BillboardPspace8770"
$firewallName = "BF V4 Billboard pSpace 8770"
$cacheVersion = "20260726-pspace-live-r3"

foreach ($path in @(
    $stageBridge,
    $stageLauncher,
    $stageAdapter,
    $targetAdapter,
    $targetHtml,
    $credentialSample,
    $sdkModule,
    $python
)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
    }
}

$bridgeText = Get-Content -LiteralPath $stageBridge -Raw -Encoding UTF8
$launcherText = Get-Content -LiteralPath $stageLauncher -Raw -Encoding UTF8
$adapterText = Get-Content -LiteralPath $stageAdapter -Raw -Encoding UTF8
foreach ($marker in @("BILLBOARD_SENSOR_IDS", "build_confirmed_billboard_extra_sensors", '"point_meta"')) {
    if (-not $bridgeText.Contains($marker)) { throw "Bridge stage marker missing: $marker" }
}
foreach ($marker in @("DEFAULT_USER", "DEFAULT_PASSWORD", '"8770"', "PSPACE_REALREAD_BATCH_SIZE")) {
    if (-not $launcherText.Contains($marker)) { throw "Launcher stage marker missing: $marker" }
}
foreach ($marker in @("__BF3D_BILLBOARD_PSPACE_LIVE__", "connectBillboardRealtime", "BF_PSPACE_WS_PORT", '"8770"', "installBackgroundControl", "soft-light")) {
    if (-not $adapterText.Contains($marker)) { throw "Adapter stage marker missing: $marker" }
}

foreach ($scriptPath in @($stageBridge, $stageLauncher)) {
    & $python -X utf8 -c "import ast,pathlib; ast.parse(pathlib.Path(r'$scriptPath').read_text(encoding='utf-8'))"
    if ($LASTEXITCODE -ne 0) { throw "Python syntax validation failed: $scriptPath" }
}

$service8768 = Get-Service -Name "BFV4PreviewWs8768" -ErrorAction Stop
$listener8768Before = Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction Stop | Select-Object -First 1
if ($service8768.Status -ne "Running" -or -not $listener8768Before) {
    throw "Existing BFV4PreviewWs8768/8768 must be healthy before deployment"
}
$pid8768Before = [int]$listener8768Before.OwningProcess
$task8094 = Get-ScheduledTask -TaskPath $taskPath -TaskName "V3AutoPreviewProxy8094" -ErrorAction Stop
if ($task8094.State -ne "Running") { throw "V3AutoPreviewProxy8094 must be running before deployment" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $v4Root "backups\8094_billboard_pspace_live_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$targetStates = [ordered]@{}
foreach ($item in @(
    @{ Name = "bridge"; Path = $targetBridge },
    @{ Name = "launcher"; Path = $targetLauncher },
    @{ Name = "adapter"; Path = $targetAdapter },
    @{ Name = "html"; Path = $targetHtml }
)) {
    $exists = Test-Path -LiteralPath $item.Path
    $targetStates[$item.Name] = [ordered]@{ path = $item.Path; existed = $exists }
    if ($exists) {
        Copy-Item -LiteralPath $item.Path -Destination (Join-Path $backup ([IO.Path]::GetFileName($item.Path))) -Force
    }
}

$existingTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$taskExisted = [bool]$existingTask
$taskWasRunning = $taskExisted -and $existingTask.State -eq "Running"
$taskXmlPath = Join-Path $backup "$taskName.xml"
if ($taskExisted) {
    Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName |
        Set-Content -LiteralPath $taskXmlPath -Encoding Unicode
}
$firewallExisted = [bool](Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue)
$firewallCreated = $false
$deployed = $false

function Restore-File {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $state = $targetStates[$Name]
    if ($state.existed) {
        $backupFile = Join-Path $backup ([IO.Path]::GetFileName($Path))
        Copy-Item -LiteralPath $backupFile -Destination $Path -Force
    }
    elseif (Test-Path -LiteralPath $Path) {
        $resolved = [IO.Path]::GetFullPath($Path)
        $allowedV3 = [IO.Path]::GetFullPath((Join-Path $v3Root "tools"))
        if (-not $resolved.StartsWith($allowedV3, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Rollback target escaped the intended tools directory: $resolved"
        }
        Remove-Item -LiteralPath $resolved -Force
    }
}

function Invoke-HttpWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$Attempts = 3
    )
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            return Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 60
        }
        catch {
            $lastError = $_
            if ($attempt -lt $Attempts) {
                Start-Sleep -Seconds 2
            }
        }
    }
    throw $lastError
}

try {
    if ($existingTask -and $existingTask.State -eq "Running") {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        Start-Sleep -Seconds 2
    }

    Copy-Item -LiteralPath $stageBridge -Destination $targetBridge -Force
    Copy-Item -LiteralPath $stageLauncher -Destination $targetLauncher -Force
    Copy-Item -LiteralPath $stageAdapter -Destination $targetAdapter -Force

    $html = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
    $pattern = "assets/bf3d-furnace-body-billboard-adapter\.js(?:\?v=[^`"']*)?"
    if ($html -notmatch $pattern) { throw "8094 HTML adapter reference was not found" }
    $html = [regex]::Replace(
        $html,
        $pattern,
        "assets/bf3d-furnace-body-billboard-adapter.js?v=$cacheVersion",
        1
    )
    [IO.File]::WriteAllText($targetHtml, $html, [Text.UTF8Encoding]::new($false))

    $action = New-ScheduledTaskAction `
        -Execute $python `
        -Argument "-X utf8 `"$targetLauncher`"" `
        -WorkingDirectory $v3Root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Days 365) `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries
    Register-ScheduledTask `
        -TaskPath $taskPath `
        -TaskName $taskName `
        -Description "Dedicated pSpace RealReadList stream for the 133-point furnace-body Billboard on port 8770." `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Force | Out-Null

    if (-not $firewallExisted) {
        New-NetFirewallRule `
            -DisplayName $firewallName `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort 8770 `
            -Profile Any `
            -RemoteAddress "10.0.0.0/8" | Out-Null
        $firewallCreated = $true
    }

    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        $task8770 = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        $listener8770 = Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction SilentlyContinue
    } while ((-not $listener8770 -or $task8770.State -ne "Running") -and (Get-Date) -lt $deadline)
    if (-not $listener8770 -or $task8770.State -ne "Running") {
        $taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
        throw "$taskName/8770 did not start; task result=$($taskInfo.LastTaskResult)"
    }

    $probe = @'
import asyncio
import json
import math
import websockets

REQUIRED = (
    "DP_total",
    "T_throat_A",
    "P_static_lower_A",
    "P_static_middle_C",
    "P_static_upper_F",
)

async def main():
    async with websockets.connect("ws://127.0.0.1:8770", open_timeout=15, max_size=25_000_000) as ws:
        for _ in range(12):
            payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            if payload.get("type") != "tick":
                continue
            values = payload.get("values") or {}
            meta = payload.get("point_meta") or {}
            quality = payload.get("data_quality") or {}
            numeric_ids = [
                key for key in meta
                if isinstance(values.get(key), (int, float)) and math.isfinite(values[key])
            ]
            result = {
                "type": payload.get("type"),
                "timestamp": payload.get("timestamp"),
                "replayMode": (payload.get("replay") or {}).get("mode"),
                "streamValueCount": len(values),
                "billboardMetaCount": len(meta),
                "billboardExpected": quality.get("billboard_expected"),
                "billboardMapped": quality.get("billboard_mapped"),
                "billboardMissingCount": len(quality.get("billboard_missing") or []),
                "requiredKeysPresent": all(key in values and key in meta for key in REQUIRED),
                "requiredNumericCount": sum(
                    1 for key in REQUIRED
                    if isinstance(values.get(key), (int, float)) and math.isfinite(values[key])
                ),
                "numericBillboardValues": len(numeric_ids),
                "qualityMetadataCount": sum(1 for key in meta if meta[key].get("quality") not in (None, "")),
            }
            print(json.dumps(result, ensure_ascii=False))
            structural_ok = (
                result["replayMode"] == "pspace_realtime"
                and result["streamValueCount"] == 140
                and result["billboardMetaCount"] == 133
                and result["billboardExpected"] == 133
                and result["billboardMapped"] == 133
                and result["billboardMissingCount"] == 0
                and result["requiredKeysPresent"]
            )
            if structural_ok and result["numericBillboardValues"] >= 100:
                return
            raise SystemExit(2)
        raise SystemExit(3)

asyncio.run(main())
'@
    $probePath = Join-Path $stageRoot "verify_billboard_pspace_8770.py"
    [IO.File]::WriteAllText($probePath, $probe, [Text.UTF8Encoding]::new($false))
    $probeOutput = & $python -X utf8 $probePath
    if ($LASTEXITCODE -ne 0) { throw "Real 8770 Billboard pSpace probe failed" }
    $probeResult = $probeOutput | Select-Object -Last 1 | ConvertFrom-Json

    $http = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/?billboard_live=$stamp"
    if ($http.StatusCode -ne 200 -or $http.Content -notmatch [regex]::Escape($cacheVersion)) {
        throw "8094 HTML cache-busted adapter reference verification failed"
    }
    $adapterHttp = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/assets/bf3d-furnace-body-billboard-adapter.js?v=$cacheVersion"
    if (
        $adapterHttp.StatusCode -ne 200 -or
        $adapterHttp.Content -notmatch "__BF3D_BILLBOARD_PSPACE_LIVE__" -or
        $adapterHttp.Content -notmatch '"8770"'
    ) {
        throw "8094 live adapter HTTP verification failed"
    }

    $service8768After = Get-Service -Name "BFV4PreviewWs8768" -ErrorAction Stop
    $listener8768After = Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction Stop | Select-Object -First 1
    if ($service8768After.Status -ne "Running" -or -not $listener8768After) {
        throw "Existing BFV4PreviewWs8768/8768 was disturbed"
    }

    $deployed = $true
    [ordered]@{
        ok = $true
        backup = $backup
        task8770 = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
        port8770 = [bool](Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction SilentlyContinue)
        firewall = $firewallName
        service8768 = $service8768After.Status.ToString()
        port8768 = $true
        process8768Unchanged = ([int]$listener8768After.OwningProcess -eq $pid8768Before)
        task8094 = (Get-ScheduledTask -TaskPath $taskPath -TaskName "V3AutoPreviewProxy8094").State.ToString()
        http8094 = $http.StatusCode
        cacheVersion = $cacheVersion
        probe = $probeResult
        bridgeSha256 = (Get-FileHash -LiteralPath $targetBridge -Algorithm SHA256).Hash
        launcherSha256 = (Get-FileHash -LiteralPath $targetLauncher -Algorithm SHA256).Hash
        adapterSha256 = (Get-FileHash -LiteralPath $targetAdapter -Algorithm SHA256).Hash
        htmlSha256 = (Get-FileHash -LiteralPath $targetHtml -Algorithm SHA256).Hash
    } | ConvertTo-Json -Depth 6
}
catch {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    if ($taskExisted) {
        $taskXml = Get-Content -LiteralPath $taskXmlPath -Raw -Encoding Unicode
        Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Xml $taskXml -Force | Out-Null
        if ($taskWasRunning) {
            Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        }
    }
    else {
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    if ($firewallCreated) {
        Remove-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue
    }
    Restore-File -Name "bridge" -Path $targetBridge
    Restore-File -Name "launcher" -Path $targetLauncher
    Restore-File -Name "adapter" -Path $targetAdapter
    Restore-File -Name "html" -Path $targetHtml
    throw
}
finally {
    if (-not $deployed) {
        Write-Warning "Deployment rolled back from $backup"
    }
}
