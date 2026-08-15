[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop | Select-Object -First 1
$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)"
$Candidates = @(
    Join-Path $Root '自动诊断服务\local_pg_ws_bridge.py'
    Join-Path $Root 'local_pg_ws_bridge.py'
)
$Files = @()
foreach ($Path in $Candidates) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { continue }
    $Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $Start = $Text.IndexOf('BASELINE_COMPARE_VARIABLES = [')
    $End = if ($Start -ge 0) { $Text.IndexOf(']', $Start) } else { -1 }
    $Block = if ($Start -ge 0 -and $End -gt $Start) { $Text.Substring($Start, $End - $Start + 1) } else { '' }
    $Files += [pscustomobject]@{
        path = $Path
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        baseline_variable_count = ([regex]::Matches($Block, '"[A-Za-z0-9_]+"')).Count
        has_cold_blast = $Block.Contains('P_blast_cold')
        has_pci_set = $Block.Contains('PCI_set')
    }
}

[pscustomobject]@{
    ok = $true
    listener_pid = [int]$Listener.OwningProcess
    executable = $Process.ExecutablePath
    command_line = $Process.CommandLine
    files = $Files
} | ConvertTo-Json -Depth 6
