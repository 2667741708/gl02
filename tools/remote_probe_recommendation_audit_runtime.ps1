$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$bridge = Join-Path $root "自动诊断服务\local_pg_ws_bridge.py"
$adapter = Join-Path $root "自动诊断服务\recommendation_adapter.py"
$service = Get-Service -Name "BFV4PreviewWs8768" -ErrorAction Stop
$serviceRegistry = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\BFV4PreviewWs8768"
$serviceParameters = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\BFV4PreviewWs8768\Parameters"
$listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

[ordered]@{
    service = if ($service) {
        [ordered]@{
            name = $service.Name
            state = $service.Status.ToString()
            pathName = $serviceRegistry.ImagePath
            application = $serviceParameters.Application
            appDirectory = $serviceParameters.AppDirectory
            appParameters = $serviceParameters.AppParameters
            appStdout = $serviceParameters.AppStdout
            appStderr = $serviceParameters.AppStderr
        }
    } else { $null }
    listener = if ($listener) {
        [ordered]@{
            pid = $listener.OwningProcess
        }
    } else { $null }
    files = [ordered]@{
        bridge = $bridge
        bridgeSha256 = (Get-FileHash -LiteralPath $bridge -Algorithm SHA256).Hash
        adapterSha256 = (Get-FileHash -LiteralPath $adapter -Algorithm SHA256).Hash
        bridgeHasAuditImport = (Get-Content -LiteralPath $bridge -Raw -Encoding UTF8).Contains("recommendation_audit_store")
    }
    logs = [ordered]@{
        runner = @(Get-Content -LiteralPath (Join-Path $root "logs\ws_8768.service.runner.log") -Tail 20 -ErrorAction SilentlyContinue)
        stdout = if ($serviceParameters.AppStdout) { @(Get-Content -LiteralPath $serviceParameters.AppStdout -Tail 40 -ErrorAction SilentlyContinue) } else { @() }
        stderr = if ($serviceParameters.AppStderr) { @(Get-Content -LiteralPath $serviceParameters.AppStderr -Tail 60 -ErrorAction SilentlyContinue) } else { @() }
    }
} | ConvertTo-Json -Depth 8
