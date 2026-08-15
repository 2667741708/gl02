[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$OutPath = Join-Path $Root 'logs\proxy_8093.service.out.log'
$ErrPath = Join-Path $Root 'logs\proxy_8093.service.err.log'
$Pattern = '16:28|16:29|16:30|17:1|20:24|20:25|query_body_temperature_statistics|model.*content|empty|Traceback|Exception|ERROR|tool_result|tool_start|assistant_mcp|execution_trace'

function Select-RecentMatches {
    param([string]$Path, [int]$Tail)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @()
    }
    return @(
        Get-Content -LiteralPath $Path -Tail $Tail -Encoding UTF8 |
            Select-String -Pattern $Pattern |
            Select-Object -Last 240 |
            ForEach-Object { $_.Line }
    )
}

[ordered]@{
    schema = 'bf.8093.body-temperature-failure-probe.v1'
    collected_at = (Get-Date).ToString('o')
    stdout = @(Select-RecentMatches -Path $OutPath -Tail 3000)
    stderr = @(Select-RecentMatches -Path $ErrPath -Tail 3000)
    stderr_tail = if (Test-Path -LiteralPath $ErrPath -PathType Leaf) {
        @(Get-Content -LiteralPath $ErrPath -Tail 240 -Encoding UTF8)
    } else { @() }
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
