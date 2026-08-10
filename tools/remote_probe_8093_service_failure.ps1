$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$logs = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs"
foreach ($name in "proxy_8093.service.runner.log", "proxy_8093.service.err.log") {
    Write-Output "FILE=$name"
    Get-Content -LiteralPath (Join-Path $logs $name) -Tail 80 -Encoding UTF8
}
