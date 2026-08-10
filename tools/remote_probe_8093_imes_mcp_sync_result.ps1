$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$registryPath = Join-Path $root '高炉前端数据\智能助手\backend\mcp_host\server_registry.json'
$serviceConfig = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$backupParent = Join-Path $root 'logs\deploy_backups'
$ports = @(8093, 8768, 8094, 8770)

$netstatLines = & "$env:SystemRoot\System32\netstat.exe" -ano -p TCP
$listeners = [ordered]@{}
foreach ($port in $ports) {
    $pattern = "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    $match = $netstatLines | Where-Object { $_ -match $pattern } | Select-Object -First 1
    $listeners[[string]$port] = if ($match -and $match -match $pattern) {
        [int]$Matches[1]
    } else {
        $null
    }
}

$service = Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction SilentlyContinue
$taskText = & "$env:SystemRoot\System32\schtasks.exe" /Query `
    /TN '\BlastFurnaceServices\BFV4PreviewProxy8093HealthCheck' /FO LIST 2>$null
$guardState = if ($LASTEXITCODE -ne 0) {
    'Missing'
} elseif ($taskText -match '(?im)^Status:\s+Running\s*$') {
    'Running'
} elseif ($taskText -match '(?im)^Status:\s+Ready\s*$') {
    'Ready'
} else {
    'Present'
}

$latest = Get-ChildItem -LiteralPath $backupParent -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '8093_imes_mcp_sync_*' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$resultPath = if ($latest) { Join-Path $latest.FullName 'deployment_result.json' } else { $null }
$deploymentResult = if ($resultPath -and (Test-Path -LiteralPath $resultPath)) {
    Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    $null
}

$registry = if (Test-Path -LiteralPath $registryPath) {
    Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    $null
}
$serviceIds = if ($registry) {
    @($registry.servers | ForEach-Object { [string]$_.server_id })
} else {
    @()
}

$config = if (Test-Path -LiteralPath $serviceConfig) {
    Get-Content -LiteralPath $serviceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    $null
}

$targets = [ordered]@{
    imes_mcp = Join-Path $root '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'
    imes_catalog = Join-Path $root '高炉前端数据\智能助手\mcp\imes_full_variable_catalog.json'
    registry = $registryPath
    extended_mcp = Join-Path $root '高炉前端数据\智能助手\mcp\bf_data_extended_mcp_server.py'
    web_mcp = Join-Path $root '高炉前端数据\智能助手\mcp\imes_web_mcp_server.py'
}
$hashes = [ordered]@{}
foreach ($name in $targets.Keys) {
    $path = $targets[$name]
    $hashes[$name] = if (Test-Path -LiteralPath $path -PathType Leaf) {
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    } else {
        $null
    }
}

[ordered]@{
    checked_at = (Get-Date).ToString('o')
    service_status = if ($service) { $service.Status.ToString() } else { 'Missing' }
    guard_state = $guardState
    listeners = $listeners
    latest_backup = if ($latest) { $latest.FullName } else { $null }
    result_present = [bool]$deploymentResult
    deployment_result = $deploymentResult
    registered_services = $serviceIds
    service_config = [ordered]@{
        registry = if ($config) { [string]$config.env.BF_QA_MCP_SERVER_REGISTRY } else { $null }
        connection_mode = if ($config) { [string]$config.env.IMES_MCP_CONNECTION_MODE } else { $null }
        db_host = if ($config) { [string]$config.env.IMES_RELAY_DB_HOST } else { $null }
        web_url = if ($config) { [string]$config.env.IMES_WEB_URL } else { $null }
    }
    hashes = $hashes
} | ConvertTo-Json -Depth 10
