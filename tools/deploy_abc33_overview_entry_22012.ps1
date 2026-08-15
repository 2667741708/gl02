$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Session = 'tools\remote_22012_session.py'
$Payload = 'tools\remote_guarded_deploy_abc33_overview_entry_8093.ps1'
$Plan = '.tmp_deploy\abc33_overview_entry_delta_plan.json'
$Page = '高炉前端数据\frontend_dashboard_v3.server.html'
$Asset = '高炉前端数据\assets\abc-furnace-rules-production.js'
$RemoteStage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_overview_entry_20260811'

& python $Session ensure --allow-agents-password --workdir $Root
if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH session is unavailable.' }

& python $Session run -- --upload-only `
    --upload "$Page=$RemoteStage\frontend_dashboard_v3.server.html" `
    --upload "$Asset=$RemoteStage\abc-furnace-rules-production.js" `
    --upload "$Plan=$RemoteStage\delta-plan.json" `
    --upload "$Payload=$RemoteStage\remote_guarded_deploy_abc33_overview_entry_8093.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed.' }

& python $Session run -- --script $Payload
if ($LASTEXITCODE -ne 0) { throw 'Guarded 8093 deployment failed.' }

& python $Session status
