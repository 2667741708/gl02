[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$OutPath = Join-Path $Root 'logs\proxy_8093.service.out.log'
$ErrPath = Join-Path $Root 'logs\proxy_8093.service.err.log'
$Patterns = '08:04|08:05|abc|initial|analysis|validation|Traceback|Exception|BrokenPipe|KeyboardInterrupt'

$OutMatches = @()
if (Test-Path -LiteralPath $OutPath -PathType Leaf) {
    $OutMatches = @(Get-Content -LiteralPath $OutPath -Tail 400 -Encoding UTF8 | Select-String -Pattern $Patterns)
}
$ErrMatches = @()
if (Test-Path -LiteralPath $ErrPath -PathType Leaf) {
    $ErrMatches = @(Get-Content -LiteralPath $ErrPath -Tail 600 -Encoding UTF8 | Select-String -Pattern $Patterns)
}

[ordered]@{
    schema = 'bug.8093.abc33-sse-failure-probe.v1'
    collected_at = (Get-Date).ToString('o')
    stdout_matches = @($OutMatches | Select-Object -Last 120 | ForEach-Object { $_.Line })
    stderr_matches = @($ErrMatches | Select-Object -Last 180 | ForEach-Object { $_.Line })
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
