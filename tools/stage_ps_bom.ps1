param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$destinationPath = [System.IO.Path]::GetFullPath($Destination)
$content = [System.IO.File]::ReadAllText($sourcePath, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($destinationPath, $content, [System.Text.UTF8Encoding]::new($true))

$bytes = [System.IO.File]::ReadAllBytes($destinationPath)
if ($bytes.Length -lt 3 -or $bytes[0] -ne 0xEF -or $bytes[1] -ne 0xBB -or $bytes[2] -ne 0xBF) {
    throw "UTF-8 BOM staging failed: $destinationPath"
}

Write-Output $destinationPath
