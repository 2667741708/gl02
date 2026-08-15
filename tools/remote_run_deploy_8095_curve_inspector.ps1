[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\remote_deploy_static_curve_inspector.ps1' -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\curve_inspector_8095' -TargetRoot 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' -HtmlName 'frontend_dashboard_v3.8095_preview.server.html' -Port 8095
exit $LASTEXITCODE
