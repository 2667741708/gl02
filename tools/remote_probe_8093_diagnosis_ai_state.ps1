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
$Response = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/diagnosis-ai-analysis?label=normal&probe=state' -TimeoutSec 45
$LogPath = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\proxy_8093.service.out.log'
$FailureLines = @(Get-Content -LiteralPath $LogPath -Tail 400 -Encoding UTF8 |
    Where-Object { $_ -like '*five-minute diagnosis AI analysis failed:*' } |
    Select-Object -Last 10)
[ordered]@{
    ok = [bool]$Response.ok
    state = [string]$Response.analysis.state
    attempt_count = [int]$Response.analysis.attempt_count
    target_label = [string]$Response.analysis.target_label
    has_analysis = $null -ne $Response.analysis.analysis
    recent_failure_lines = $FailureLines
} | ConvertTo-Json -Depth 4
