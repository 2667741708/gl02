$ErrorActionPreference = 'Stop'
function Get-NetstatPid([int]$Port) {
    foreach ($line in @(netstat -ano -p tcp)) {
        if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") { return [int]$Matches[1] }
    }
    return $null
}
$task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V4BillboardPspace8770'
$svc = Get-Service -Name 'BFV4PreviewProxy8093'
$bridge = Get-Content -LiteralPath 'F:\高炉炼铁项目-real-sensor-v2_V3\tools\pspace_8092_realtime_bridge.py' -Raw -Encoding UTF8
$html = Get-Content -LiteralPath 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\foreman_trend_preview.html' -Raw -Encoding UTF8
[ordered]@{
    task_state = [string]$task.State
    proxy8093 = [string]$svc.Status
    listeners = [ordered]@{ '8093' = Get-NetstatPid 8093; '8094' = Get-NetstatPid 8094; '8768' = Get-NetstatPid 8768; '8770' = Get-NetstatPid 8770 }
    bridge_markers = [ordered]@{ extra = $bridge.Contains('SIO_GL02_BT_T0136'); water = $bridge.Contains('SIO_GL02_BT_T0056'); co = $bridge.Contains('SIO_CC_GF2_T0112'); h2 = $bridge.Contains('SIO_CC_GF2_T0111') }
    html_marker = if ($html.Contains('20260806-pspace-extra-r3')) { '20260806-pspace-extra-r3' } else { $null }
} | ConvertTo-Json -Depth 5
