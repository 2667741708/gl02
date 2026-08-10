$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$names = @(
    "GL02_PGHOST",
    "GL02_PGPORT",
    "GL02_PGDATABASE",
    "GL02_PGUSER",
    "GL02_PGPASSWORD",
    "GL02_READER_PASSWORD",
    "GL02_PGADMIN_PASSWORD"
)
$values = @{}
foreach ($name in $names) {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    $values[$name] = $value
}

foreach ($required in @("GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD")) {
    if (-not $values[$required]) {
        throw "Missing remote environment variable: $required"
    }
}

$sha256 = [Security.Cryptography.SHA256]::Create()
function Get-SecretFingerprint([string]$Value) {
    if (-not $Value) {
        return ""
    }
    $bytes = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))
    return ([BitConverter]::ToString($bytes)).Replace("-", "")
}

$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
    throw "psql not found: $psql"
}
$env:PGPASSWORD = $values["GL02_PGPASSWORD"]
try {
    $query = @"
SELECT json_build_object(
    'database', current_database(),
    'user', current_user,
    'server_version', current_setting('server_version'),
    'server_addr', inet_server_addr(),
    'server_port', inet_server_port(),
    'can_create_database', has_database_privilege(current_user, current_database(), 'CREATE'),
    'can_insert_diagnosis', has_table_privilege(current_user, 'bf_sensor.diagnosis_snapshots', 'INSERT'),
    'login_roles', (
        SELECT json_agg(json_build_object(
            'role', rolname,
            'superuser', rolsuper,
            'create_db', rolcreatedb,
            'create_role', rolcreaterole
        ) ORDER BY rolname)
        FROM pg_roles
        WHERE rolcanlogin
    )
)::text;
"@
    $raw = & $psql -w `
        -h $values["GL02_PGHOST"] `
        -p $values["GL02_PGPORT"] `
        -U $values["GL02_PGUSER"] `
        -d $values["GL02_PGDATABASE"] `
        -tA `
        -v ON_ERROR_STOP=1 `
        -c $query
    if ($LASTEXITCODE -ne 0) {
        throw "Runtime PostgreSQL account query failed: $($raw -join ' ')"
    }

    $readerRaw = $null
    if ($values["GL02_READER_PASSWORD"]) {
        $env:PGPASSWORD = $values["GL02_READER_PASSWORD"]
        $readerRaw = & $psql -w `
            -h "127.0.0.1" `
            -p $values["GL02_PGPORT"] `
            -U "gl02_reader" `
            -d $values["GL02_PGDATABASE"] `
            -tA `
            -v ON_ERROR_STOP=1 `
            -c "SELECT current_user || '|' || has_table_privilege(current_user, 'bf_sensor.diagnosis_snapshots', 'SELECT') || '|' || has_table_privilege(current_user, 'bf_sensor.diagnosis_snapshots', 'INSERT');"
        if ($LASTEXITCODE -ne 0) {
            throw "Reader PostgreSQL account query failed: $($readerRaw -join ' ')"
        }
    }

    $adminRaw = $null
    if ($values["GL02_PGADMIN_PASSWORD"]) {
        $env:PGPASSWORD = $values["GL02_PGADMIN_PASSWORD"]
        $adminRaw = & $psql -w `
            -h "127.0.0.1" `
            -p $values["GL02_PGPORT"] `
            -U "postgres" `
            -d $values["GL02_PGDATABASE"] `
            -tA `
            -v ON_ERROR_STOP=1 `
            -c "SELECT current_user || '|' || rolsuper FROM pg_roles WHERE rolname = current_user;"
        if ($LASTEXITCODE -ne 0) {
            throw "Admin PostgreSQL account query failed: $($adminRaw -join ' ')"
        }
    }
} finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

[ordered]@{
    host = $values["GL02_PGHOST"]
    port = $values["GL02_PGPORT"]
    database = $values["GL02_PGDATABASE"]
    runtime_user = $values["GL02_PGUSER"]
    runtime_password_set = [bool]$values["GL02_PGPASSWORD"]
    runtime_password_length = ([string]$values["GL02_PGPASSWORD"]).Length
    runtime_password_sha256 = Get-SecretFingerprint $values["GL02_PGPASSWORD"]
    reader_password_set = [bool]$values["GL02_READER_PASSWORD"]
    reader_password_length = ([string]$values["GL02_READER_PASSWORD"]).Length
    reader_password_sha256 = Get-SecretFingerprint $values["GL02_READER_PASSWORD"]
    admin_password_set = [bool]$values["GL02_PGADMIN_PASSWORD"]
    admin_password_length = ([string]$values["GL02_PGADMIN_PASSWORD"]).Length
    admin_password_sha256 = Get-SecretFingerprint $values["GL02_PGADMIN_PASSWORD"]
    runtime_query = (($raw -join "") | ConvertFrom-Json)
    reader_query = ($readerRaw -join "").Trim()
    admin_query = ($adminRaw -join "").Trim()
} | ConvertTo-Json -Depth 5
