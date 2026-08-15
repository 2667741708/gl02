[CmdletBinding()]
param(
    [ValidateSet('TERMSRV/10.30.220.12')]
    [string]$CredentialTarget = 'TERMSRV/10.30.220.12',
    [ValidateSet('administrator')]
    [string]$ExpectedUser = 'administrator',
    [string]$PasswordPath = "$env:LOCALAPPDATA\Codex\secrets\reliable-ssh\22012.pw",
    [string]$ReliableSshPasswordPath = 'C:\Users\hmw20\.codex\secrets\reliable-ssh-10-30-220-12.password',
    [ValidateSet('Auto', 'WindowsCredential', 'ReliableSshPasswordFile')]
    [string]$Source = 'Auto'
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

if (-not ('BfWindowsCredentialReader' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class BfWindowsCredentialReader
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct NativeCredential
    {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);

    [DllImport("advapi32.dll", SetLastError = true)]
    private static extern void CredFree(IntPtr credential);

    public static Tuple<string, string> ReadDomainPassword(string target)
    {
        IntPtr pointer;
        if (!CredRead(target, 2, 0, out pointer))
        {
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        }
        try
        {
            NativeCredential credential = Marshal.PtrToStructure<NativeCredential>(pointer);
            if (credential.CredentialBlob == IntPtr.Zero)
            {
                throw new InvalidOperationException("The credential secret pointer is unavailable.");
            }
            if (credential.CredentialBlobSize == 0)
            {
                throw new InvalidOperationException("The credential secret is empty.");
            }
            if (credential.CredentialBlobSize % 2 != 0)
            {
                throw new InvalidOperationException("The credential secret is not UTF-16 text.");
            }
            string password = Marshal.PtrToStringUni(
                credential.CredentialBlob,
                checked((int)credential.CredentialBlobSize / 2)
            );
            return Tuple.Create(credential.UserName ?? string.Empty, password ?? string.Empty);
        }
        finally
        {
            CredFree(pointer);
        }
    }
}
'@
}

$RecoveredPassword = $null
$Credential = $null
$SecretSource = $null
if ($Source -in @('Auto', 'WindowsCredential')) {
    try {
        $Credential = [BfWindowsCredentialReader]::ReadDomainPassword($CredentialTarget)
    }
    catch {
        if ($Source -eq 'WindowsCredential') {
            throw 'The authorized Windows credential secret is unavailable for export.'
        }
    }
    if ($Credential) {
        $CredentialUser = [string]$Credential.Item1
        $CredentialLeafUser = ($CredentialUser -split '[\\/]')[-1]
        if (-not $CredentialLeafUser.Equals($ExpectedUser, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The Windows credential username does not match the authorized SSH account.'
        }
        $RecoveredPassword = [string]$Credential.Item2
        $SecretSource = 'windows_credential_manager'
    }
}
if (-not $RecoveredPassword -and $Source -in @('Auto', 'ReliableSshPasswordFile')) {
    if (-not (Test-Path -LiteralPath $ReliableSshPasswordPath -PathType Leaf)) {
        throw 'The authorized Reliable SSH password file is unavailable.'
    }
    $IdentityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $SourceAcl = Get-Acl -LiteralPath $ReliableSshPasswordPath
    $UnexpectedSourceAllow = @($SourceAcl.Access | Where-Object {
        $_.AccessControlType -eq 'Allow' -and
        $_.IdentityReference.Value -notin @($IdentityName, 'NT AUTHORITY\SYSTEM')
    })
    if ($SourceAcl.Owner -ne $IdentityName -or -not $SourceAcl.AreAccessRulesProtected -or $UnexpectedSourceAllow.Count -gt 0) {
        throw 'The authorized Reliable SSH password file ACL is not sufficiently restricted.'
    }
    $RecoveredPassword = (Get-Content -LiteralPath $ReliableSshPasswordPath -Raw -Encoding UTF8).Trim()
    $SecretSource = 'reliable_ssh_password_file'
}
if ([string]::IsNullOrWhiteSpace($RecoveredPassword)) {
    throw 'The authorized credential source contains an empty secret.'
}
if ($RecoveredPassword.StartsWith('stored in the protected Codex', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The authorized credential source contains the redaction marker.'
}

$PasswordDirectory = Split-Path -Parent $PasswordPath
New-Item -ItemType Directory -Path $PasswordDirectory -Force | Out-Null
$TemporaryPath = Join-Path $PasswordDirectory ('.22012.pw.restoring-' + [Guid]::NewGuid().ToString('N'))
$IdentityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
try {
    [IO.File]::WriteAllText($TemporaryPath, $RecoveredPassword + [Environment]::NewLine, $Utf8NoBom)
    $IcaclsArguments = @(
        $TemporaryPath
        '/inheritance:r'
        '/grant:r'
        "${IdentityName}:(F)"
        '*S-1-5-18:(F)'
    )
    & "$env:SystemRoot\System32\icacls.exe" @IcaclsArguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "icacls failed with exit code $LASTEXITCODE"
    }
    [IO.File]::Move($TemporaryPath, $PasswordPath, $true)
}
finally {
    $RecoveredPassword = $null
    $Credential = $null
    if (Test-Path -LiteralPath $TemporaryPath -PathType Leaf) {
        Remove-Item -LiteralPath $TemporaryPath -Force
    }
}

$ProtectedAcl = Get-Acl -LiteralPath $PasswordPath
$UnexpectedAllow = @($ProtectedAcl.Access | Where-Object {
    $_.AccessControlType -eq 'Allow' -and
    $_.IdentityReference.Value -notin @($IdentityName, 'NT AUTHORITY\SYSTEM')
})
if ($UnexpectedAllow.Count -gt 0 -or -not $ProtectedAcl.AreAccessRulesProtected) {
    throw 'The restored password file ACL is not restricted to the current user and SYSTEM.'
}

[ordered]@{
    ok = $true
    schema = 'bf.22012.authorized-credential-restore.v1'
    credential_target = $CredentialTarget
    expected_user = $ExpectedUser
    username_verified = $true
    secret_source = $SecretSource
    password_file = $PasswordPath
    password_value_emitted = $false
    inheritance_protected = $ProtectedAcl.AreAccessRulesProtected
} | ConvertTo-Json -Depth 4
