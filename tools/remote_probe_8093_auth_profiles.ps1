[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Path = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Config = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json
$Names = @($Config.env.PSObject.Properties.Name | Where-Object { $_ -like 'BF_LOGIN*' } | Sort-Object)
$Users = @(([string]$Config.env.BF_LOGIN_USERS) -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Usable = 0
foreach ($User in $Users) {
    $Key = (($User -replace '[^A-Za-z0-9]+', '_').ToUpperInvariant()).Trim('_')
    $PasswordName = "BF_LOGIN_${Key}_PASSWORD"
    if ($Names -contains $PasswordName -or $Names -contains 'BF_LOGIN_PASSWORD') { $Usable += 1 }
}
[pscustomobject]@{
    schema = 'ops.8093.auth-profile-names.v1'
    read_only = $true
    property_names = $Names
    has_operator_pair = ($Names -contains 'BF_LOGIN_OPERATOR_USERNAME' -and $Names -contains 'BF_LOGIN_OPERATOR_PASSWORD')
    has_admin_pair = ($Names -contains 'BF_LOGIN_ADMIN_USERNAME' -and $Names -contains 'BF_LOGIN_ADMIN_PASSWORD')
    configured_user_count = $Users.Count
    usable_user_count = $Usable
    secret_values_returned = $false
} | ConvertTo-Json -Depth 4
