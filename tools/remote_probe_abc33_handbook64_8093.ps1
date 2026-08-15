$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$targets = @(
    '自动诊断服务\abc_rule_guidance.py',
    '自动诊断服务\abc_rule_catalog.py',
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\frontend_dashboard_v3.server.html'
)
$protected = @(
    '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html',
    '高炉前端数据\assets\bf3d-billboard-adapter.js'
)

function Get-PortPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

$files = foreach ($relativePath in ($targets + $protected)) {
    $path = Join-Path $root $relativePath
    [ordered]@{
        path = $relativePath
        exists = Test-Path -LiteralPath $path
        sha256 = if (Test-Path -LiteralPath $path) {
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        } else { $null }
    }
}

$listeners = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $listeners["p$port"] = Get-PortPid $port
}

[ordered]@{
    checked_at = (Get-Date).ToString('o')
    computer = $env:COMPUTERNAME
    pwsh = $PSVersionTable.PSVersion.ToString()
    root_exists = Test-Path -LiteralPath $root
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
        BFV4PreviewWs8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    }
    listeners = $listeners
    files = $files
}|ConvertTo-Json -Depth 6
