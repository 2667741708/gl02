[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\remote_deploy_static_curve_inspector.ps1' -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\curve_inspector_8096' -TargetRoot 'F:\炽穹·高炉炼铁大模型V3' -HtmlName 'frontend_dashboard_v3.server.html' -Port 8096
exit $LASTEXITCODE
