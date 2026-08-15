[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InputPath,
    [string]$OutputPath = '.tmp\8093-mcp-parallel-guest-20260813\preflight.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$InputPath = (Resolve-Path -LiteralPath $InputPath).Path
$OutputPath = Join-Path $Root $OutputPath
$Envelope = Get-Content -LiteralPath $InputPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Match = [regex]::Match([string]$Envelope.stdout, '(?s)\[remote\].*?\r?\n(?<json>\{.*\})\r?\n\[exit\]')
if (-not $Match.Success) { throw 'Remote preflight JSON payload was not found.' }
$Preflight = $Match.Groups['json'].Value | ConvertFrom-Json
if (-not $Preflight.ok -or $Preflight.production_write_performed) {
    throw 'Remote preflight contract failed.'
}
[IO.File]::WriteAllText($OutputPath, ($Preflight | ConvertTo-Json -Depth 10), $Utf8NoBom)
$OutputPath
