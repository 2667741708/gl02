param(
    [Parameter(Mandatory = $true)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Path).Path
$tokens = $null
$errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $resolved,
    [ref]$tokens,
    [ref]$errors
)
if ($errors.Count -gt 0) {
    $errors | ForEach-Object {
        Write-Error "line=$($_.Extent.StartLineNumber) column=$($_.Extent.StartColumnNumber): $($_.Message)"
    }
    exit 1
}
Write-Output "PowerShell syntax OK: $resolved"
