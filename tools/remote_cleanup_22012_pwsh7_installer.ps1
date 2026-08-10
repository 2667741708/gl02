[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$allowedRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$targets = @(
    'C:\Users\Administrator\AppData\Local\Temp\PowerShell_7.6.4_x64.msi',
    'C:\Users\Administrator\AppData\Local\Temp\verify_22012_pwsh7.ps1'
)
$removed = @()
foreach ($target in $targets) {
    $parent = Split-Path -Parent $target
    if ($parent -ne $allowedRoot) {
        throw "Cleanup target is outside the approved temp root: $target"
    }
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
        $removed += $target
    }
}

[ordered]@{
    schema = 'bf.remote.pwsh7.cleanup.v1'
    ok = $true
    removed = $removed
    pwsh_preserved = (Test-Path -LiteralPath 'C:\Program Files\PowerShell\7\pwsh.exe' -PathType Leaf)
} | ConvertTo-Json -Depth 3
