$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ports = @{}
$netstat = @(netstat.exe -ano)
foreach ($port in @(8093, 8768, 8094, 8770, 8891)) {
    $line = @($netstat | Where-Object { $_ -match "LISTENING\s+(\d+)\s*$" -and $_ -match ":$port\s" })[0]
    $ports["port_$port"] = if ($line -and $line -match "LISTENING\s+(\d+)\s*$") { [int]$matches[1] } else { $null }
}
$syncTask = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'HeatPerformanceQualitySync' -ErrorAction SilentlyContinue
$pageHttp = try { [int](Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/' -TimeoutSec 10).StatusCode } catch { $null }
$apiHttp = try { [int](Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?limit=1' -TimeoutSec 10).StatusCode } catch { $null }

[ordered]@{
    checked_at = (Get-Date).ToString('o')
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service BFV4PreviewProxy8093).Status.ToString()
        BFV4PreviewWs8768 = (Get-Service BFV4PreviewWs8768).Status.ToString()
    }
    ports = $ports
    sync_task = if ($syncTask) { $syncTask.State.ToString() } else { $null }
    page_http = $pageHttp
    api_http = $apiHttp
} | ConvertTo-Json -Depth 6
