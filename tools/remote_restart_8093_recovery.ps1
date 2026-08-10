$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$config = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action restart -ConfigPath $config
Get-Service -Name BFV4PreviewProxy8093 | Select-Object Status,Name
