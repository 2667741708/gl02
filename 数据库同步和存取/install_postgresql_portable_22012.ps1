$ErrorActionPreference = "Stop"

$ZipUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.13-1-windows-x64-binaries.zip"
$InstallerDir = "F:\installers"
$ZipPath = Join-Path $InstallerDir "postgresql-16.13-1-windows-x64-binaries.zip"
$ExtractDir = "F:\PostgreSQL\extract-16.13"
$InstallRoot = "F:\PostgreSQL\16"
$DataDir = "F:\PostgreSQL\16\data"
$LogDir = "F:\PostgreSQL\16\logs"
$ServiceName = "postgresql-x64-16"
$Port = "5432"
$DatabaseName = "bf_trend"
$AppUser = "gl02_sync"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function New-Password {
    $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] 32
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function Set-MachineEnv {
    param([string]$Name, [string]$Value)
    [Environment]::SetEnvironmentVariable($Name, $Value, "Machine")
    Set-Item -Path "Env:$Name" -Value $Value
}

New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallRoot) | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ScriptRoot "logs") | Out-Null

$AdminPassword = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_PASSWORD", "Machine")
if (-not $AdminPassword) {
    $AdminPassword = New-Password
    Set-MachineEnv -Name "GL02_PGADMIN_PASSWORD" -Value $AdminPassword
}

$AppPassword = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
if (-not $AppPassword) {
    $AppPassword = New-Password
}
Set-MachineEnv -Name "GL02_PGHOST" -Value "127.0.0.1"
Set-MachineEnv -Name "GL02_PGPORT" -Value $Port
Set-MachineEnv -Name "GL02_PGDATABASE" -Value $DatabaseName
Set-MachineEnv -Name "GL02_PGUSER" -Value $AppUser
Set-MachineEnv -Name "GL02_PGPASSWORD" -Value $AppPassword

if (-not (Test-Path $ZipPath)) {
    Write-Host "Downloading PostgreSQL binaries..."
    Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
}

if (-not (Test-Path (Join-Path $InstallRoot "bin\postgres.exe"))) {
    Write-Host "Extracting PostgreSQL binaries..."
    if (Test-Path $ExtractDir) {
        Remove-Item -Path $ExtractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractDir -Force
    $extractedRoot = Join-Path $ExtractDir "pgsql"
    if (-not (Test-Path $extractedRoot)) {
        $extractedRoot = (Get-ChildItem -Path $ExtractDir -Directory | Select-Object -First 1).FullName
    }
    if (Test-Path $InstallRoot) {
        Remove-Item -Path $InstallRoot -Recurse -Force
    }
    Move-Item -Path $extractedRoot -Destination $InstallRoot
}

$BinDir = Join-Path $InstallRoot "bin"
$PsqlPath = Join-Path $BinDir "psql.exe"
$InitdbPath = Join-Path $BinDir "initdb.exe"
$PgCtlPath = Join-Path $BinDir "pg_ctl.exe"
$PgLog = Join-Path $LogDir "postgresql.log"

if (-not (Test-Path $PsqlPath)) {
    throw "psql.exe not found under $BinDir"
}

if (-not (Test-Path (Join-Path $DataDir "PG_VERSION"))) {
    Write-Host "Initializing PostgreSQL data directory..."
    if (Test-Path $DataDir) {
        takeown /F $DataDir /R /D Y | Out-Null
        icacls $DataDir /grant "Administrators:(OI)(CI)F" /T | Out-Null
        Remove-Item -Path $DataDir -Recurse -Force
    }
    $pwFile = Join-Path $InstallerDir "pg_pw.tmp"
    Set-Content -Path $pwFile -Value $AdminPassword -Encoding ASCII
    & $InitdbPath -D $DataDir -U postgres -A scram-sha-256 --pwfile=$pwFile -E UTF8 --locale=C --locale-provider=libc
    if ($LASTEXITCODE -ne 0) {
        throw "initdb failed with exit code $LASTEXITCODE"
    }
    Remove-Item -Path $pwFile -Force -ErrorAction SilentlyContinue
}

$confPath = Join-Path $DataDir "postgresql.conf"
$conf = Get-Content -Path $confPath -Raw
if ($conf -notmatch "listen_addresses\s*=\s*'127.0.0.1'") {
    Add-Content -Path $confPath -Value "`nlisten_addresses = '127.0.0.1'`nport = $Port`nshared_buffers = '1GB'`neffective_cache_size = '4GB'`nmaintenance_work_mem = '512MB'`ncheckpoint_timeout = '15min'`nmax_wal_size = '8GB'`ntimezone = 'Asia/Shanghai'`n"
}

icacls $InstallRoot /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
icacls $InstallRoot /grant "Administrators:(OI)(CI)F" /T | Out-Null

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "Registering PostgreSQL service..."
    & $PgCtlPath register -N $ServiceName -D $DataDir -S auto
}

Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
$env:PGPASSWORD = $AdminPassword
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline) {
    $ready = & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ready.Trim() -eq "1") {
        break
    }
    Start-Sleep -Seconds 2
}
$ready = & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1"
if ($ready.Trim() -ne "1") {
    throw "PostgreSQL did not become ready."
}

$dbExists = & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DatabaseName'"
if ((-not $dbExists) -or $dbExists.Trim() -ne "1") {
    & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DatabaseName ENCODING 'UTF8' TEMPLATE template0"
}

$roleSql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$AppUser') THEN
    CREATE ROLE $AppUser LOGIN PASSWORD '$AppPassword';
  ELSE
    ALTER ROLE $AppUser WITH LOGIN PASSWORD '$AppPassword';
  END IF;
END
`$`$;
GRANT ALL PRIVILEGES ON DATABASE $DatabaseName TO $AppUser;
"@
& $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -v ON_ERROR_STOP=1 -c $roleSql
& $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d $DatabaseName -v ON_ERROR_STOP=1 -c "GRANT CREATE, USAGE ON SCHEMA public TO $AppUser;"

$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
& $Python (Join-Path $ScriptRoot "src\init_pg.py")

Write-Host "PostgreSQL portable deployment is ready."
