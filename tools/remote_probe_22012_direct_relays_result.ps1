$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$deployRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups"
$latest = Get-ChildItem -LiteralPath $deployRoot -Directory -ErrorAction Stop |
    Where-Object { $_.Name -like "22012_direct_source_relays_*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $latest) { throw "没有找到直接转发部署备份目录" }
$resultPath = Join-Path $latest.FullName "deployment_result.json"
[ordered]@{
    path = $latest.FullName
    result_exists = Test-Path -LiteralPath $resultPath
    files = @(Get-ChildItem -LiteralPath $latest.FullName | Select-Object -ExpandProperty Name)
    result = if (Test-Path -LiteralPath $resultPath) {
        Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else { $null }
} | ConvertTo-Json -Depth 10
