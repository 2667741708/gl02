param(
    [string]$BaseUri = 'http://10.30.220.12:8093'
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$Bootstrap = Invoke-RestMethod -Uri ($BaseUri + '/api/qa/bootstrap') -WebSession $Session -TimeoutSec 30
$ConversationId = [string]$Bootstrap.conversation.id
$Conversation = Invoke-RestMethod -Uri ($BaseUri + '/api/qa/conversation?id=' + [uri]::EscapeDataString($ConversationId)) -WebSession $Session -TimeoutSec 30
$Messages = @($Conversation.messages)
$LatestAssistant = $Messages | Where-Object { $_.role -eq 'assistant' } | Select-Object -Last 1
$LatestUser = $Messages | Where-Object { $_.role -eq 'user' } | Select-Object -Last 1

[pscustomobject]@{
    schema = 'ops.8093.guest-last-answer.readonly.v1'
    access_mode = [string]$Bootstrap.access_mode
    conversation_id = $ConversationId
    message_count = $Messages.Count
    user_created_at = [string]$LatestUser.created_at
    user_content = [string]$LatestUser.content
    assistant_created_at = [string]$LatestAssistant.created_at
    assistant_content = [string]$LatestAssistant.content
    realtime_unverified_declared = ([string]$LatestAssistant.content).Contains('实时数据库未核实')
} | ConvertTo-Json -Depth 4
