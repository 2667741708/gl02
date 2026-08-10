[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw '该配置器只允许使用 PowerShell 7 Core。'
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$pwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
if (-not (Test-Path -LiteralPath $pwshPath -PathType Leaf)) {
    throw "找不到 PowerShell 7：$pwshPath"
}

$terminalState = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState'
$settingsPath = Join-Path $terminalState 'settings.json'
if (-not (Test-Path -LiteralPath $settingsPath -PathType Leaf)) {
    throw "找不到 Windows Terminal 配置：$settingsPath"
}

$settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding utf8 | ConvertFrom-Json
$profileGuid = '{5da7d3e7-9fc4-4c4e-ae3d-7ee8d28d9d70}'
$profiles = @($settings.profiles.list)
$pwshProfile = $profiles | Where-Object { $_.guid -eq $profileGuid } | Select-Object -First 1
if ($null -eq $pwshProfile) {
    $pwshProfile = [pscustomobject]@{
        guid = $profileGuid
        name = 'PowerShell 7'
        commandline = $pwshPath
        hidden = $false
    }
    $profiles += $pwshProfile
}
else {
    $pwshProfile.name = 'PowerShell 7'
    $pwshProfile.commandline = $pwshPath
    $pwshProfile.hidden = $false
}

foreach ($profile in $profiles) {
    $commandProperty = $profile.PSObject.Properties['commandline']
    if ($null -ne $commandProperty -and $commandProperty.Value -like '*WindowsPowerShell*v1.0*powershell.exe*') {
        if ($null -eq $profile.PSObject.Properties['hidden']) {
            $profile | Add-Member -NotePropertyName hidden -NotePropertyValue $true
        }
        else {
            $profile.hidden = $true
        }
    }
}

$settings.profiles.list = $profiles
$settings.defaultProfile = $profileGuid

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = Join-Path $terminalState "settings.before-pwsh7.$stamp.json"
$tempPath = Join-Path $terminalState 'settings.pwsh7.tmp.json'
Copy-Item -LiteralPath $settingsPath -Destination $backupPath

try {
    $json = $settings | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($tempPath, $json + [Environment]::NewLine, $utf8NoBom)
    $check = Get-Content -LiteralPath $tempPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($check.defaultProfile -ne $profileGuid) {
        throw '默认配置写入验证失败。'
    }
    Move-Item -LiteralPath $tempPath -Destination $settingsPath -Force
}
finally {
    if (Test-Path -LiteralPath $tempPath) {
        Remove-Item -LiteralPath $tempPath -Force
    }
}

[ordered]@{
    schema = 'bf.windows-terminal.pwsh7-default.v1'
    ok = $true
    settings = $settingsPath
    backup = $backupPath
    default_profile = $profileGuid
    executable = $pwshPath
    windows_powershell_profile_hidden = $true
} | ConvertTo-Json -Depth 3
