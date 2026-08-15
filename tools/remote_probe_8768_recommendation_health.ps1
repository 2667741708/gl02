[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [int]$Tail = 400
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$BridgePath = Join-Path $Root '自动诊断服务\local_pg_ws_bridge.py'
$CandidateLogs = @(
    (Join-Path $Root 'logs\ws_8768.service.out.log'),
    (Join-Path $Root 'logs\ws_8768.service.err.log')
)
$Patterns = 'recommendation|audit|Traceback|error|failed|exception'
$LogEvidence = foreach ($Path in $CandidateLogs) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        [ordered]@{ path = $Path; exists = $false; matches = @() }
        continue
    }
    $Matches = @(
        Get-Content -LiteralPath $Path -Tail $Tail -Encoding UTF8 |
            Select-String -Pattern $Patterns -CaseSensitive:$false |
            ForEach-Object { $_.Line }
    )
    [ordered]@{
        path = $Path
        exists = $true
        last_write = (Get-Item -LiteralPath $Path).LastWriteTime.ToString('o')
        matches = @($Matches | Select-Object -Last 80)
    }
}
$Listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

[ordered]@{
    schema = 'ops.8768.recommendation-health-probe.v1'
    collected_at = (Get-Date).ToString('o')
    service = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    listener_pid = if ($Listener) { $Listener.OwningProcess } else { $null }
    bridge_sha256 = if (Test-Path -LiteralPath $BridgePath -PathType Leaf) {
        (Get-FileHash -LiteralPath $BridgePath -Algorithm SHA256).Hash
    } else { $null }
    logs = @($LogEvidence)
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
