[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Response = Invoke-WebRequest -Uri 'http://127.0.0.1:8094/api/qa/bootstrap' -UseBasicParsing -TimeoutSec 30 -SkipHttpErrorCheck
$Body = [string]$Response.Content
[pscustomobject]@{
    schema = 'ops.8094.qa-isolation-probe.v1'
    read_only = $true
    status = [int]$Response.StatusCode
    content_type = [string]$Response.Headers.'Content-Type'
    body_preview = $Body.Substring(0, [Math]::Min(500, $Body.Length))
} | ConvertTo-Json -Depth 4
