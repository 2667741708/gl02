[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RelativePaths = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py',
    '高炉前端数据\智能助手\mcp\bf_data_mcp_server.py',
    '高炉前端数据\智能助手\mcp\bf_data_extended_mcp_server.py',
    '高炉前端数据\智能助手\mcp\catalog\calculation_tools.json'
)
$Files = @(
    foreach ($RelativePath in $RelativePaths) {
        $Path = Join-Path $Root $RelativePath
        [ordered]@{
            relative_path = $RelativePath
            exists = Test-Path -LiteralPath $Path -PathType Leaf
            length = if (Test-Path -LiteralPath $Path -PathType Leaf) { (Get-Item -LiteralPath $Path).Length } else { $null }
            sha256 = if (Test-Path -LiteralPath $Path -PathType Leaf) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash } else { $null }
        }
    }
)
[ordered]@{
    schema = 'bf.8093-body-stats-target-probe.v1'
    files = $Files
    production_write_performed = $false
} | ConvertTo-Json -Depth 5
