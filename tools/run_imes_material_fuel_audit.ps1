[CmdletBinding()]
param(
    [string]$OutputPath = "logs\imes_material_fuel_audit_20260806.json",
    [ValidateSet('environment', 'approved-historical-operations')]
    [string]$CredentialProfile = 'environment'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$loader = Join-Path $projectRoot 'PT\load_imes_vastbase_local.ps1'
$pythonLibs = Join-Path $projectRoot '.tmp_pylibs'
$auditScript = Join-Path $PSScriptRoot 'audit_imes_material_fuel_metrics.py'
$resolvedOutput = Join-Path $projectRoot $OutputPath

try {
    . $loader
    $env:IMES_DB_HOST = '10.30.220.12'
    $env:IMES_DB_PORT = '15433'
    $env:PYTHONPATH = (Resolve-Path -LiteralPath $pythonLibs).Path
    python $auditScript `
        --host $env:IMES_DB_HOST `
        --port ([int]$env:IMES_DB_PORT) `
        --database $env:IMES_DB_NAME `
        --credential-profile $CredentialProfile `
        --limit 8 `
        --output $resolvedOutput
    if ($LASTEXITCODE -ne 0) {
        throw "IMES material/fuel audit exited with code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:IMES_DB_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:IMES_DB_USER -ErrorAction SilentlyContinue
}
