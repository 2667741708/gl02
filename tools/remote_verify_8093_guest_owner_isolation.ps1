[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$BaseUri = 'http://127.0.0.1:8093'
$ConfigPath = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding utf8 | ConvertFrom-Json
$User = @(([string]$Config.env.BF_LOGIN_USERS) -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }) | Select-Object -First 1
if (-not $User) { throw 'No configured login user is available.' }
$Key = (($User -replace '[^A-Za-z0-9]+', '_').ToUpperInvariant()).Trim('_')
$PasswordProperty = "BF_LOGIN_${Key}_PASSWORD"
$Password = [string]$Config.env.$PasswordProperty
if (-not $Password) { $Password = [string]$Config.env.BF_LOGIN_PASSWORD }
if (-not $Password) { throw 'Configured login password is unavailable.' }

$GuestSession = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$Guest = Invoke-RestMethod -Uri ($BaseUri + '/api/qa/bootstrap') -WebSession $GuestSession -TimeoutSec 30
$GuestConversation = [string]$Guest.conversation.id

$OwnerSession = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$LoginBody = @{ username = $User; password = $Password } | ConvertTo-Json -Compress
$Login = Invoke-RestMethod -Method Post -Uri ($BaseUri + '/api/auth/login') -WebSession $OwnerSession -ContentType 'application/json' -Headers @{ Origin = $BaseUri } -Body $LoginBody -TimeoutSec 30
$Owner = Invoke-RestMethod -Uri ($BaseUri + '/api/qa/bootstrap') -WebSession $OwnerSession -TimeoutSec 30
$OwnerConversation = [string]$Owner.conversation.id

function Get-IdHash {
    param([string]$Value)
    $Bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $Hash = [Security.Cryptography.SHA256]::HashData($Bytes)
    return ([Convert]::ToHexString($Hash)).Substring(0, 16)
}

$Result = [pscustomobject]@{
    schema = 'ops.8093.guest-owner-isolation.v1'
    ok = ($Login.ok -and $GuestConversation -and $OwnerConversation -and $GuestConversation -ne $OwnerConversation)
    guest_access_mode = [string]$Guest.access_mode
    owner_access_mode = [string]$Owner.access_mode
    guest_conversation_hash = Get-IdHash $GuestConversation
    owner_conversation_hash = Get-IdHash $OwnerConversation
    conversation_ids_differ = ($GuestConversation -ne $OwnerConversation)
    configured_identity_count = 1
    cross_owner_pair_not_tested = $true
    model_requests = 0
    secret_values_returned = $false
}
$Password = $null
$LoginBody = $null
$Result | ConvertTo-Json -Depth 4
if (-not $Result.ok) { exit 2 }
