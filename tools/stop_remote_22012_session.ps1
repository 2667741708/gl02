[CmdletBinding()]
param([string]$PythonPath = '')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$SessionScript = Join-Path $PSScriptRoot 'remote_22012_session.py'
if (-not $PythonPath) {
    $PythonPath = (Get-Command -Name python -ErrorAction Stop).Source
}

& $PythonPath $SessionScript stop
if ($LASTEXITCODE -ne 0) {
    throw 'Persistent 220.12 SSH session could not be stopped.'
}
