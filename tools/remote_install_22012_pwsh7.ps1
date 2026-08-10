$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$msiPath = 'C:\Users\Administrator\AppData\Local\Temp\PowerShell_7.6.4_x64.msi'
$verifyScript = 'C:\Users\Administrator\AppData\Local\Temp\verify_22012_pwsh7.ps1'
$expectedHash = 'D11942DF52FD12470169797ABFA4781D9480EFDC81000BA4FA55A5B921ED8DD0'
$pwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'

if (-not (Test-Path -LiteralPath $msiPath -PathType Leaf)) {
    throw "PowerShell MSI is missing: $msiPath"
}
if (-not (Test-Path -LiteralPath $verifyScript -PathType Leaf)) {
    throw "Verification script is missing: $verifyScript"
}

$actualHash = (Get-FileHash -LiteralPath $msiPath -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "PowerShell MSI SHA-256 mismatch: $actualHash"
}
$signature = Get-AuthenticodeSignature -LiteralPath $msiPath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike 'CN=Microsoft Corporation*') {
    throw "PowerShell MSI signature is invalid: $($signature.Status)"
}

function Get-ProtectedListeners {
    @(8093, 8094, 8768, 8770, 5432 | ForEach-Object {
        $port = [int]$_
        $row = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
        [ordered]@{
            port = $port
            listening = ($null -ne $row)
            pid = if ($row) { [int]$row.OwningProcess } else { $null }
        }
    })
}

$listenersBefore = Get-ProtectedListeners
$alreadyInstalled = Test-Path -LiteralPath $pwshPath -PathType Leaf
$installExitCode = 0
if (-not $alreadyInstalled) {
    $arguments = @('/i', $msiPath, '/qn', '/norestart', 'ADD_PATH=1', 'REGISTER_MANIFEST=1')
    $installer = Start-Process -FilePath 'msiexec.exe' -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
    $installExitCode = [int]$installer.ExitCode
    if ($installExitCode -notin @(0, 3010)) {
        throw "PowerShell MSI installation failed: exit=$installExitCode"
    }
}

if (-not (Test-Path -LiteralPath $pwshPath -PathType Leaf)) {
    throw "PowerShell 7 executable was not installed: $pwshPath"
}

$verificationText = & $pwshPath -NoLogo -NoProfile -NonInteractive -File $verifyScript
if ($LASTEXITCODE -ne 0) {
    throw "PowerShell 7 verification failed: exit=$LASTEXITCODE"
}
$verification = $verificationText | ConvertFrom-Json
if (-not $verification.ok) {
    throw 'PowerShell 7 verification returned ok=false'
}

$listenersAfter = Get-ProtectedListeners
$listenerFailures = @()
foreach ($before in $listenersBefore) {
    $after = $listenersAfter | Where-Object { $_.port -eq $before.port } | Select-Object -First 1
    if ($before.listening -and (-not $after.listening -or $after.pid -ne $before.pid)) {
        $listenerFailures += "port=$($before.port),before=$($before.pid),after=$($after.pid)"
    }
}
if ($listenerFailures.Count -ne 0) {
    throw "Protected listener changed during installation: $($listenerFailures -join ';')"
}

[ordered]@{
    schema = 'bf.remote.pwsh7.install.v1'
    ok = $true
    already_installed = $alreadyInstalled
    install_exit_code = $installExitCode
    msi_sha256 = $actualHash
    msi_signature = [string]$signature.Status
    pwsh_path = $pwshPath
    pwsh_version = $verification.ps_version
    verification = $verification
    listeners_before = $listenersBefore
    listeners_after = $listenersAfter
    reboot_required = ($installExitCode -eq 3010)
} | ConvertTo-Json -Depth 10
