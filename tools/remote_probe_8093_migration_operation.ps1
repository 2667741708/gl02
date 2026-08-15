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

$Path = 'C:\Users\Administrator\AppData\Local\Temp\OPS-8093-PWSH7-RUNTIME-MIGRATION-20260811\operation.json'
if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Operation plan missing: $Path" }
$Plan = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json
[ordered]@{
    ok = $true
    read_only = $true
    sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    schema = [string]$Plan.schema
    requirement_id = [string]$Plan.requirement_id
    mode = [string]$Plan.mode
    target = [string]$Plan.target
    expected_target_sha256 = [string]$Plan.expected_target_sha256
    expected_staged_sha256 = [string]$Plan.expected_staged_sha256
} | ConvertTo-Json -Depth 4
