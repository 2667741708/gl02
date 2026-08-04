[CmdletBinding()]
param(
    [switch]$Relay
)

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'imes_vastbase.local.env'
$allowedKeys = @(
    'IMES_DB_HOST',
    'IMES_DB_PORT',
    'IMES_DB_NAME',
    'IMES_DB_USER',
    'IMES_DB_PASSWORD'
)

if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
    throw "Vastbase local credential file not found: $configPath"
}

foreach ($line in Get-Content -LiteralPath $configPath -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#')) {
        continue
    }

    $parts = $trimmed.Split('=', 2)
    if ($parts.Count -ne 2) {
        throw "Invalid local credential entry in $configPath"
    }

    $key = $parts[0].Trim()
    $value = $parts[1]
    if ($key -notin $allowedKeys) {
        throw "Unsupported local credential key: $key"
    }
    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}

if ($Relay) {
    $env:IMES_DB_HOST = '127.0.0.1'
    $env:IMES_DB_PORT = '15433'
}

$requiredKeys = @('IMES_DB_HOST', 'IMES_DB_PORT', 'IMES_DB_NAME', 'IMES_DB_USER', 'IMES_DB_PASSWORD')
$missingKeys = @($requiredKeys | Where-Object {
    -not [Environment]::GetEnvironmentVariable($_, 'Process')
})
if ($missingKeys.Count -gt 0) {
    throw "Missing required Vastbase settings: $($missingKeys -join ', ')"
}

Write-Host "Vastbase local configuration loaded: $env:IMES_DB_HOST`:$env:IMES_DB_PORT/$env:IMES_DB_NAME; user=$env:IMES_DB_USER; password=SET"

