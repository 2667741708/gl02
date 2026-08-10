$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$path='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\自动诊断服务\local_pg_ws_bridge.py'
Write-Output ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash)
