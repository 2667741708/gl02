param(
    [string]$Database = 'bf_trend',
    [string]$SqlPath = 'tools/sql/foreman_pressure_quartiles_20260806.sql'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$migrationPath = Join-Path $projectRoot $SqlPath
$psqlPath = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'

if (-not (Test-Path -LiteralPath $psqlPath)) {
    throw "PostgreSQL 16 psql not found: $psqlPath"
}
if (-not (Test-Path -LiteralPath $migrationPath)) {
    throw "Migration SQL not found: $migrationPath"
}

$credentialPath = $null
$credentialText = $null
$docsPath = Join-Path $projectRoot 'docs'
foreach ($candidate in Get-ChildItem -LiteralPath $docsPath -Filter '*.md' -File) {
    $candidateText = Get-Content -LiteralPath $candidate.FullName -Raw -Encoding UTF8
    if ($candidateText.Contains('port=18000') -and $candidateText.Contains('GL02_PGADMIN_PASSWORD')) {
        $credentialPath = $candidate.FullName
        $credentialText = $candidateText
        break
    }
}
if (-not $credentialPath) {
    throw 'Authorised PostgreSQL credential document was not found'
}
$localSectionEnd = $credentialText.IndexOf('server=10.30.220.12')
if ($localSectionEnd -lt 0) {
    throw 'Local PostgreSQL credential section boundary was not found'
}
$localSection = $credentialText.Substring(0, $localSectionEnd)
$passwordMatch = [regex]::Match($localSection, '(?m)^password=(.+)$')
if (-not $passwordMatch.Success) {
    throw 'Local PostgreSQL administrator password was not found in the authorised credential document'
}

$previousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $passwordMatch.Groups[1].Value.Trim()
    & $psqlPath -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 18000 -U postgres -d $Database -c 'SELECT current_user, current_database(), version();'
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL identity check failed with exit code $LASTEXITCODE"
    }
    $baselineTable = (& $psqlPath -w -tA -h 127.0.0.1 -p 18000 -U postgres -d $Database -c "SELECT to_regclass('bf_sensor.daily_baselines');").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Baseline table probe failed with exit code $LASTEXITCODE"
    }
    if (-not $baselineTable) {
        $schemaPath = $null
        foreach ($candidate in Get-ChildItem -LiteralPath $projectRoot -Recurse -Filter 'schema.sql' -File) {
            $schemaText = Get-Content -LiteralPath $candidate.FullName -Raw -Encoding UTF8
            if ($schemaText.Contains('CREATE TABLE IF NOT EXISTS bf_sensor.daily_baselines')) {
                $schemaPath = $candidate.FullName
                break
            }
        }
        if (-not $schemaPath) {
            throw 'Authoritative automatic-diagnosis schema.sql was not found'
        }
        & $psqlPath -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 18000 -U postgres -d $Database -f $schemaPath
        if ($LASTEXITCODE -ne 0) {
            throw "Automatic-diagnosis schema bootstrap failed with exit code $LASTEXITCODE"
        }
    }
    & $psqlPath -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 18000 -U postgres -d $Database -f $migrationPath
    if ($LASTEXITCODE -ne 0) {
        throw "Quartile migration failed with exit code $LASTEXITCODE"
    }
    $auditSchemaPath = Get-ChildItem -LiteralPath $projectRoot -Recurse -Filter 'recommendation_audit_schema.sql' -File | Select-Object -First 1 -ExpandProperty FullName
    if (-not $auditSchemaPath) {
        throw 'Recommendation audit schema was not found'
    }
    & $psqlPath -w -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 18000 -U postgres -d $Database -f $auditSchemaPath
    if ($LASTEXITCODE -ne 0) {
        throw "Recommendation audit v2 migration failed with exit code $LASTEXITCODE"
    }
}
finally {
    if ($null -eq $previousPassword) {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
    else {
        $env:PGPASSWORD = $previousPassword
    }
}
