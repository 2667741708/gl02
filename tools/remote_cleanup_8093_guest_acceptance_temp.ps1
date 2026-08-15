$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Target = 'C:\Users\Administrator\AppData\Local\Temp\bf_accept_abc33_contextual_assistant.ps1'
if (Test-Path -LiteralPath $Target -PathType Leaf) {
    Remove-Item -LiteralPath $Target -Force
}

[pscustomobject]@{
    ok = -not (Test-Path -LiteralPath $Target)
    removed = $true
    target = $Target
} | ConvertTo-Json -Compress
