$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$AcceptanceScript = Join-Path $PSScriptRoot 'bf_accept_abc33_contextual_assistant.ps1'
if (-not (Test-Path -LiteralPath $AcceptanceScript -PathType Leaf)) {
    throw "Acceptance script is missing: $AcceptanceScript"
}

& $AcceptanceScript -Port 8093 -GuestShared
