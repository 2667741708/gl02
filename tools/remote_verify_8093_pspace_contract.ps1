$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$service = Get-Service -Name 'BFV4PreviewProxy8093'
$listener = Get-NetTCPConnection -State Listen -LocalPort 8093 | Select-Object -First 1
if (-not $listener) { throw '8093 listener is missing' }
$process = Get-CimInstance -ClassName Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess)
$pageUrl = 'http://127.0.0.1:8093/frontend_dashboard_v3.server.html?verify=20260805'
$assetUrl = 'http://127.0.0.1:8093/assets/bf-core-metrics-pspace-live-8093.js?verify=20260805'
$page = Invoke-WebRequest -UseBasicParsing -Uri $pageUrl -TimeoutSec 15
$asset = Invoke-WebRequest -UseBasicParsing -Uri $assetUrl -TimeoutSec 15

$checks = [ordered]@{
    ServiceRunning = $service.Status -eq 'Running'
    HttpPage200 = $page.StatusCode -eq 200
    HttpAsset200 = $asset.StatusCode -eq 200
    PageHasSchema = $page.Content.Contains('bf.core-metrics.pspace-live.8093.v1')
    PageHasAsset = $page.Content.Contains('bf-core-metrics-pspace-live-8093.js')
    PageHasHistoryMergeFix = $page.Content.Contains('BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093')
    AssetHasSchema = $asset.Content.Contains('bf.core-metrics.pspace-live.8093.v1')
    AssetUses8770 = $asset.Content.Contains('8770')
    AssetHasStaleFallback = $asset.Content.Contains('staleAfterMs')
}
$ok = -not ($checks.Values -contains $false)
$result = [pscustomobject]@{
    Ok = $ok
    Service = $service.Status.ToString()
    ListenerPid = [int]$listener.OwningProcess
    ProcessName = $process.Name
    Checks = $checks
}
$result | ConvertTo-Json -Depth 5
if (-not $ok) { throw '8093 pSpace contract verification failed' }
