$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$path = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html'
$text = Get-Content -LiteralPath $path -Raw -Encoding UTF8

[pscustomobject]@{
  Computer = $env:COMPUTERNAME
  PathExists = Test-Path -LiteralPath $path
  Hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
  Service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HasThreeColumn = $text.Contains('OPS-8093-OVERVIEW-THREE-COLUMN-V12')
  HasOptimizationCockpit = $text.Contains('OptimizationEngineCockpitLayout')
  HasFastNav = $text.Contains('REQ-8093-FAST-IN-APP-NAV-20260715')
  HasReload = $text.Contains('window.location.hash=hash;window.location.reload()')
} | ConvertTo-Json -Compress
