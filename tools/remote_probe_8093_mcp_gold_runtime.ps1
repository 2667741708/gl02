[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$RelativeTargets = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\mcp_host\client_manager.py',
    '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
)
$Hashes = [ordered]@{}
foreach ($Relative in $RelativeTargets) {
    $Path = Join-Path $Root $Relative
    $Hashes[$Relative] = if (Test-Path -LiteralPath $Path -PathType Leaf) {
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    } else { $null }
}

$McpHealthHttp = 0
$McpHealth = $null
try {
    $Response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 20
    $McpHealthHttp = [int]$Response.StatusCode
    $McpHealth = $Response.Content | ConvertFrom-Json
}
catch {
    if ($_.Exception.Response) { $McpHealthHttp = [int]$_.Exception.Response.StatusCode }
    else { throw }
}

$BootstrapHttp = 0
$AccessMode = $null
try {
    $Bootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 20
    $BootstrapHttp = 200
    $AccessMode = [string]$Bootstrap.access_mode
}
catch {
    if ($_.Exception.Response) { $BootstrapHttp = [int]$_.Exception.Response.StatusCode }
    else { throw }
}

$Ollama = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 20
[ordered]@{
    schema = 'bf.8093-mcp-gold-runtime-probe.v1'
    ok = $true
    collected_at = (Get-Date).ToString('o')
    service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    listeners = [ordered]@{
        '8093' = Get-ListenerPid -Port 8093
        '8094' = Get-ListenerPid -Port 8094
        '8768' = Get-ListenerPid -Port 8768
        '8770' = Get-ListenerPid -Port 8770
        '5432' = Get-ListenerPid -Port 5432
        '11434' = Get-ListenerPid -Port 11434
    }
    target_hashes = $Hashes
    http_8093 = [int](Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?probe=mcp-gold-20260814' -TimeoutSec 20).StatusCode
    ollama_ok = [bool]$Ollama.ok
    ollama_model = [string]$Ollama.model
    mcp_health_http = $McpHealthHttp
    mcp_health_ok = if ($McpHealth) { [bool]$McpHealth.ok } else { $false }
    mcp_health = $McpHealth
    qa_bootstrap_http = $BootstrapHttp
    qa_access_mode = $AccessMode
    model_request_count = 0
    production_write_performed = $false
} | ConvertTo-Json -Depth 10
