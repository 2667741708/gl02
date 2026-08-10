$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$relativeFiles = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py',
    '高炉前端数据\智能助手\mcp\catalog\heat_analysis.json'
)

$listeners = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $row = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)[0]
    $listeners[[string]$port] = if ($row) { [int]$row.OwningProcess } else { $null }
}

$hashes = @{}
foreach ($relative in $relativeFiles) {
    $path = Join-Path $root $relative
    $hashes[$relative] = if (Test-Path -LiteralPath $path -PathType Leaf) {
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    } else {
        $null
    }
}

$healthCode = $null
try {
    $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 20
    $healthCode = [int]$health.StatusCode
} catch {
    $healthCode = 0
}

$task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFV4PreviewProxy8093HealthCheck' -ErrorAction SilentlyContinue
$result = [ordered]@{
    service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    guard_task_state = if ($task) { $task.State.ToString() } else { $null }
    listeners = $listeners
    hashes = $hashes
    mcp_health_http = $healthCode
}
$result | ConvertTo-Json -Depth 6
