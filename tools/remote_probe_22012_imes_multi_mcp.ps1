$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$mcp = Join-Path $root '高炉前端数据\智能助手\mcp\imes_relay_mcp_server.py'
$runner = Join-Path $root '高炉前端数据\智能助手\mcp\run_imes_mcp_22012.cmd'
$secret = Join-Path $root 'PT\imes_vastbase.local.env'
$python = 'C:\Program Files\Python311\python.exe'

[ordered]@{
    root_exists = Test-Path -LiteralPath $root -PathType Container
    mcp_exists = Test-Path -LiteralPath $mcp -PathType Leaf
    mcp_sha256 = if (Test-Path -LiteralPath $mcp -PathType Leaf) {
        (Get-FileHash -LiteralPath $mcp -Algorithm SHA256).Hash
    } else {
        $null
    }
    runner_exists = Test-Path -LiteralPath $runner -PathType Leaf
    secret_exists = Test-Path -LiteralPath $secret -PathType Leaf
    python_exists = Test-Path -LiteralPath $python -PathType Leaf
} | ConvertTo-Json -Compress
