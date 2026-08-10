$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$logs = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs"
foreach ($name in "preview_ws_8769.log", "preview_ws_8769.error.log", "preview_proxy_8094.error.log") {
    Write-Output "FILE=$name"
    $path = Join-Path $logs $name
    if (Test-Path -LiteralPath $path) {
        Get-Content -LiteralPath $path -Tail 100 -Encoding UTF8
    } else {
        Write-Output "<missing>"
    }
}
