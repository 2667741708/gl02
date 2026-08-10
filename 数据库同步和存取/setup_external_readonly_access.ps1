param(
    [string]$ClientCidr = $env:DB_CLIENT_CIDR,
    [string]$ReaderUser = "gl02_reader",
    [string]$DatabaseName = "bf_trend",
    [string]$SchemaName = "bf_sensor",
    [string]$AdminUser = "postgres",
    [string]$PsqlPath = "",
    [string]$DataDir = "",
    [switch]$RestartPostgres,
    [switch]$NoFirewall
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $ClientCidr) {
    throw "DB_CLIENT_CIDR is required, for example 192.168.43.140/32. Refusing to expose PostgreSQL broadly."
}
if ($ClientCidr -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$') {
    throw "Only explicit IPv4 CIDR is accepted, for example 192.168.43.140/32. Got: $ClientCidr"
}
foreach ($name in @($ReaderUser, $DatabaseName, $SchemaName, $AdminUser)) {
    if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Unsafe SQL identifier: $name"
    }
}

function New-Password {
    $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function SqlLiteral {
    param([string]$Value)
    "'" + $Value.Replace("'", "''") + "'"
}

if (-not $PsqlPath) {
    $candidates = @(
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "F:\PostgreSQL\16\bin\psql.exe"
    )
    $PsqlPath = ($candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1)
}
if (-not $PsqlPath -or -not (Test-Path -LiteralPath $PsqlPath)) {
    throw "psql.exe not found. Pass -PsqlPath."
}

if (-not $DataDir) {
    $candidates = @(
        "C:\Program Files\PostgreSQL\16\data",
        "F:\PostgreSQL\16\data"
    )
    $DataDir = ($candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ "postgresql.conf") } | Select-Object -First 1)
}
if (-not $DataDir) {
    throw "PostgreSQL data directory not found. Pass -DataDir."
}

$AdminPassword = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_PASSWORD", "Machine")
if (-not $AdminPassword) {
    $AdminPassword = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_PASSWORD", "User")
}
if (-not $AdminPassword) {
    $AdminPassword = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
    $AdminUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
}
if (-not $AdminPassword -or -not $AdminUser) {
    throw "Missing PostgreSQL admin credentials. Set GL02_PGADMIN_PASSWORD for postgres or GL02_PGUSER/GL02_PGPASSWORD for a superuser."
}

$ReaderPassword = [Environment]::GetEnvironmentVariable("GL02_READER_PASSWORD", "Machine")
if (-not $ReaderPassword) {
    $ReaderPassword = New-Password
    [Environment]::SetEnvironmentVariable("GL02_READER_PASSWORD", $ReaderPassword, "Machine")
}

$env:PGPASSWORD = $AdminPassword
$readerPasswordSql = SqlLiteral $ReaderPassword
$readerUserSql = SqlLiteral $ReaderUser

$roleSql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $readerUserSql) THEN
    CREATE ROLE $ReaderUser LOGIN PASSWORD $readerPasswordSql;
  ELSE
    ALTER ROLE $ReaderUser WITH LOGIN PASSWORD $readerPasswordSql;
  END IF;
END
`$`$;
GRANT CONNECT ON DATABASE $DatabaseName TO $ReaderUser;
"@

& $PsqlPath -h 127.0.0.1 -p 5432 -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c $roleSql
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create or update reader role."
}

$grantSql = @"
GRANT USAGE ON SCHEMA $SchemaName TO $ReaderUser;
GRANT SELECT ON ALL TABLES IN SCHEMA $SchemaName TO $ReaderUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA $SchemaName GRANT SELECT ON TABLES TO $ReaderUser;
"@
$appUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
if ($appUser -and $appUser -match '^[A-Za-z_][A-Za-z0-9_]*$') {
    $grantSql += "`nALTER DEFAULT PRIVILEGES FOR ROLE $appUser IN SCHEMA $SchemaName GRANT SELECT ON TABLES TO $ReaderUser;`n"
}
& $PsqlPath -h 127.0.0.1 -p 5432 -U $AdminUser -d $DatabaseName -v ON_ERROR_STOP=1 -c $grantSql
if ($LASTEXITCODE -ne 0) {
    throw "Failed to grant readonly privileges."
}

$confPath = Join-Path $DataDir "postgresql.conf"
$hbaPath = Join-Path $DataDir "pg_hba.conf"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$conf = Get-Content -LiteralPath $confPath -Raw
$restartRequired = $false
if ($conf -match "(?m)^\s*#?\s*listen_addresses\s*=") {
    $newConf = [regex]::Replace($conf, "(?m)^\s*#?\s*listen_addresses\s*=.*$", "listen_addresses = '*'")
} else {
    $newConf = $conf.TrimEnd() + "`r`nlisten_addresses = '*'`r`n"
}
if ($newConf -ne $conf) {
    [System.IO.File]::WriteAllText($confPath, $newConf, $Utf8NoBom)
    $restartRequired = $true
}

$hba = Get-Content -LiteralPath $hbaPath -Raw
$begin = "# GL02 reader external access begin"
$end = "# GL02 reader external access end"
$block = "$begin`r`nhost    $DatabaseName    $ReaderUser    $ClientCidr    scram-sha-256`r`n$end"
if ($hba -match [regex]::Escape($begin)) {
    $hba = [regex]::Replace($hba, "(?s)$([regex]::Escape($begin)).*?$([regex]::Escape($end))", $block)
} else {
    $hba = $hba.TrimEnd() + "`r`n`r`n$block`r`n"
}
[System.IO.File]::WriteAllText($hbaPath, $hba, $Utf8NoBom)

& $PsqlPath -h 127.0.0.1 -p 5432 -U $AdminUser -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_reload_conf();"

if (-not $NoFirewall) {
    $ruleName = "GL02 PostgreSQL readonly $ClientCidr"
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 5432 `
        -RemoteAddress $ClientCidr | Out-Null
}

if ($RestartPostgres -and $restartRequired) {
    Restart-Service -Name "postgresql-x64-16" -Force
    $restartRequired = $false
}

[PSCustomObject]@{
    ok = $true
    database = $DatabaseName
    schema = $SchemaName
    reader_user = $ReaderUser
    reader_password_env = "GL02_READER_PASSWORD"
    client_cidr = $ClientCidr
    psql = $PsqlPath
    data_dir = $DataDir
    restart_required = $restartRequired
    firewall_rule = if ($NoFirewall) { "" } else { "GL02 PostgreSQL readonly $ClientCidr" }
} | ConvertTo-Json -Depth 4
