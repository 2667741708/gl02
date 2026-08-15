[CmdletBinding()]
param([string]$ProbeLabel = 'persistent-ssh-reuse')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

[pscustomobject]@{
    schema = 'bf.remote.pwsh-file-probe.v1'
    ok = $true
    probe_label = $ProbeLabel
    ps_edition = $PSVersionTable.PSEdition
    ps_version = $PSVersionTable.PSVersion.ToString()
    process_id = $PID
    computer_name = $env:COMPUTERNAME
    console_output_encoding = [Console]::OutputEncoding.WebName
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json -Compress
