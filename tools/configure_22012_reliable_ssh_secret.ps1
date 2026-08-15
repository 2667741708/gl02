[CmdletBinding()]
param(
    [string]$SourceConfig = 'C:\Users\hmw20\.ssh\jngt_ssh_config',
    [string]$PasswordPath = "$env:LOCALAPPDATA\Codex\secrets\reliable-ssh\22012.pw"
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

if (-not (Test-Path -LiteralPath $SourceConfig -PathType Leaf)) {
    throw "SSH source config is missing: $SourceConfig"
}

$SourceText = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8
$PasswordMatch = [regex]::Match(
    $SourceText,
    '(?m)^\s*#\s*SSH password:\s*(?<password>[^\r\n]+)\r?$'
)
$PasswordDirectory = Split-Path -Parent $PasswordPath
New-Item -ItemType Directory -Path $PasswordDirectory -Force | Out-Null

$Migrated = $false
if ($PasswordMatch.Success -and -not $PasswordMatch.Groups['password'].Value.Trim().StartsWith(
    'stored in the protected Codex',
    [StringComparison]::OrdinalIgnoreCase
)) {
    $Password = $PasswordMatch.Groups['password'].Value.Trim()
    if ([string]::IsNullOrWhiteSpace($Password)) {
        throw 'The SSH password entry is empty.'
    }
    [IO.File]::WriteAllText($PasswordPath, $Password + [Environment]::NewLine, $Utf8NoBom)
    $Replacement = '# SSH password: stored in the protected Codex reliable-SSH password file.'
    $RedactedText = $SourceText.Substring(0, $PasswordMatch.Index) +
        $Replacement +
        $SourceText.Substring($PasswordMatch.Index + $PasswordMatch.Length)
    [IO.File]::WriteAllText($SourceConfig, $RedactedText, $Utf8NoBom)
    $Password = $null
    $Migrated = $true
}
elseif (-not (Test-Path -LiteralPath $PasswordPath -PathType Leaf)) {
    throw 'No SSH password entry or protected password file was found.'
}

$ProtectedPassword = (Get-Content -LiteralPath $PasswordPath -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($ProtectedPassword)) {
    throw 'Protected password file is empty.'
}
if ($ProtectedPassword.StartsWith(
    'stored in the protected Codex',
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw 'Protected password file contains the redaction marker; restore the authorized SSH secret before reconnecting.'
}
$ProtectedPassword = $null

$IdentityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Acl = Get-Acl -LiteralPath $PasswordPath
if ($Acl.Owner -ne $IdentityName) {
    throw "Protected password file owner drifted: $($Acl.Owner)"
}
$IcaclsArguments = @(
    $PasswordPath
    '/inheritance:r'
    '/grant:r'
    "${IdentityName}:(F)"
    '*S-1-5-18:(F)'
)
& "$env:SystemRoot\System32\icacls.exe" @IcaclsArguments | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "icacls failed with exit code $LASTEXITCODE"
}

[Environment]::SetEnvironmentVariable('BF_22012_SSH_PASSWORD_FILE', $PasswordPath, 'User')
$env:BF_22012_SSH_PASSWORD_FILE = $PasswordPath

$ProtectedAcl = Get-Acl -LiteralPath $PasswordPath
$UnexpectedAllow = @($ProtectedAcl.Access | Where-Object {
    $_.AccessControlType -eq 'Allow' -and
    $_.IdentityReference.Value -notin @($IdentityName, 'NT AUTHORITY\SYSTEM')
})
if ($UnexpectedAllow.Count -gt 0) {
    throw 'Protected password file has an unexpected allow ACE.'
}
$RedactedSourceText = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8
$RedactedComment = [regex]::Match(
    $RedactedSourceText,
    '(?m)^\s*#\s*SSH password:\s*(?<value>[^\r\n]+)\r?$'
)
$SourceConfigRedacted = $RedactedComment.Success -and
    $RedactedComment.Groups['value'].Value.Trim().StartsWith(
        'stored in the protected Codex',
        [StringComparison]::OrdinalIgnoreCase
    )

[ordered]@{
    ok = $true
    schema = 'bf.reliable-ssh-secret.v1'
    migrated_from_plaintext_comment = $Migrated
    source_config_redacted = $SourceConfigRedacted
    password_file = $PasswordPath
    password_value_emitted = $false
    owner = $ProtectedAcl.Owner
    inheritance_protected = $ProtectedAcl.AreAccessRulesProtected
    user_environment_reference = 'BF_22012_SSH_PASSWORD_FILE'
} | ConvertTo-Json -Depth 4
