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

$Body = @{
    model = 'chiqiong-blast-furnace:latest'
    messages = @(@{ role = 'user'; content = '只回复：正常' })
    stream = $false
    think = $false
    options = @{ num_predict = 4 }
} | ConvertTo-Json -Depth 5
$Timer = [Diagnostics.Stopwatch]::StartNew()
$Response = Invoke-RestMethod -Method Post -Uri 'http://10.30.220.12:11434/api/chat' -ContentType 'application/json; charset=utf-8' -Body $Body -TimeoutSec 60
$Timer.Stop()

[pscustomobject]@{
    ok = $true
    schema = 'bf.22012.ollama-chat-probe.v1'
    model = [string]$Response.model
    done = [bool]$Response.done
    response_present = -not [string]::IsNullOrWhiteSpace([string]$Response.message.content)
    total_duration_ms = [math]::Round($Timer.Elapsed.TotalMilliseconds, 3)
} | ConvertTo-Json -Depth 4
