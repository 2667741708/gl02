[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core or later is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Files = @(
    (Join-Path $PSScriptRoot 'remote_probe_abc33_b4_score_source_8093.ps1'),
    (Join-Path $PSScriptRoot 'remote_probe_abc33_b4_score_source_files_8093.ps1'),
    (Join-Path $PSScriptRoot 'remote_guarded_deploy_abc33_b4_score_source_8093.ps1'),
    (Join-Path $PSScriptRoot 'deploy_abc33_b4_score_source_22012.ps1'),
    (Join-Path $PSScriptRoot 'build_python_native_artifact.ps1'),
    (Join-Path $PSScriptRoot 'benchmark_22012_ssh_command_latency.ps1')
)
$Results = @()
foreach ($File in $Files) {
    if (-not (Test-Path -LiteralPath $File -PathType Leaf)) { throw "Missing script: $File" }
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($File, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -gt 0) { throw "PowerShell parse failed for $File`: $($Errors[0].Message)" }
    $Results += [pscustomobject]@{ path = $File; parsed = $true }
}
[pscustomobject]@{ schema = 'bf.abc33-b4-score-source.local-script-check.v1'; ok = $true; scripts = $Results } | ConvertTo-Json -Depth 4
