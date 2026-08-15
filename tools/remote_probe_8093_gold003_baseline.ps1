[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '高炉前端数据\智能助手\backend\mcp_host\domain_router.py'
$CrossSourceTarget = Join-Path $Root '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
$ProxyTarget = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$Ports = @(8093, 8094, 8768, 8770, 5432, 11434)
$PidMap = [ordered]@{}
foreach ($Port in $Ports) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    $PidMap[[string]$Port] = if ($Listener) { [int]$Listener.OwningProcess } else { $null }
}
$Head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
$TargetStatus = @(& $GitExe -C $Root status --short -- '高炉前端数据/智能助手/backend/mcp_host/domain_router.py')
$CrossSourceStatus = @(& $GitExe -C $Root status --short -- '高炉前端数据/智能助手/backend/mcp_host/cross_source_executor.py')
$ProxyStatus = @(& $GitExe -C $Root status --short -- '高炉前端数据/智能助手/backend/ollama_proxy_server.py')
$McpHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 30
$Ollama = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 30

[ordered]@{
    schema = 'ops.8093.gold003-baseline.v1'
    git_head = $Head
    target = $Target
    target_sha256 = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    target_git_status = $TargetStatus
    cross_source_target = $CrossSourceTarget
    cross_source_sha256 = (Get-FileHash -LiteralPath $CrossSourceTarget -Algorithm SHA256).Hash
    cross_source_git_status = $CrossSourceStatus
    proxy_target = $ProxyTarget
    proxy_sha256 = (Get-FileHash -LiteralPath $ProxyTarget -Algorithm SHA256).Hash
    proxy_git_status = $ProxyStatus
    service_status = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    listener_pids = $PidMap
    mcp_health_ok = [bool]$McpHealth.ok
    ollama_ok = [bool]$Ollama.ok
} | ConvertTo-Json -Depth 6
