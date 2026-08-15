$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Candidates = @(
    (Join-Path $Root '自动诊断服务\thermal_trend_rule.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\thermal_trend_rule.py'),
    (Join-Path $Root 'thermal_trend_rule.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\config\thermal_trend_rule.v1.json')
)
@($Candidates | ForEach-Object {
    [ordered]@{
        path = $_
        exists = Test-Path -LiteralPath $_ -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $_ -PathType Leaf) {
            (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash
        } else { $null }
    }
}) | ConvertTo-Json -Depth 4
