[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Stage,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][string]$PlanHash,
    [Parameter(Mandatory)][string]$BatchHash
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Python = 'C:/Program Files/Python311/pythonw.exe'
$Batch = Join-Path $Stage 'batch.py'
$Plan = Join-Path $Stage 'templates.remaining.plan.json'
$Collector = Join-Path $Stage 'collector.py'
foreach ($Path in @($Python,$Batch,$Plan,$Collector,$Root)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw 'Missing launch input' }
    if ($Path.Contains('"')) { throw 'Invalid quote in path' }
}
if ($Output.Contains('"')) { throw 'Invalid quote in output' }
if ((Get-FileHash -LiteralPath $Plan -Algorithm SHA256).Hash -ne $PlanHash) { throw 'Plan hash mismatch' }
if ((Get-FileHash -LiteralPath $Batch -Algorithm SHA256).Hash -ne $BatchHash) { throw 'Batch hash mismatch' }
if (Test-Path -LiteralPath $Output) { throw 'Output exists; inspect instead of replaying' }
$ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
$ResolvedOutput = [IO.Path]::GetFullPath($Output)
$AllowedPrefix = (Join-Path $ResolvedRoot 'logs') + [IO.Path]::DirectorySeparatorChar
if (-not $ResolvedOutput.StartsWith($AllowedPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Output must stay below runtime logs' }
$CommandLine = '"' + $Python + '" -X utf8 "' + $Batch + '" --root "' + $Root + '" --plan "' + $Plan + '" --collector "' + $Collector + '" --output "' + $Output + '" --execute'
# WMI owns the new process; pythonw prevents a visible console and the batch
# lifetime is independent of an SSH channel or the invoking process tree.
$Created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine=$CommandLine; CurrentDirectory=$Root }
if ($Created.ReturnValue -ne 0) { throw "Independent launch failed: $($Created.ReturnValue)" }
[pscustomobject]@{ started=$true; pid=$Created.ProcessId; output=$Output; automatic_replay=$false } | ConvertTo-Json -Compress
