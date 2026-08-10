$ErrorActionPreference = "Stop"

$InstallerUrl = "https://get.enterprisedb.com/postgresql/postgresql-16.13-1-windows-x64.exe"
$InstallerDir = "F:\installers"
$InstallerTemp = "F:\installers\tmp"
$InstallerPath = Join-Path $InstallerDir "postgresql-16.13-1-windows-x64.exe"
$InstallRoot = "F:\PostgreSQL\16"
$DataDir = "F:\PostgreSQL\16\data"
$ServiceName = "postgresql-x64-16"
$Port = "5432"
$DatabaseName = "bf_trend"
$AppUser = "gl02_sync"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PsqlPath = Join-Path $InstallRoot "bin\psql.exe"

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
New-Item -ItemType Directory -Force -Path $InstallerTemp | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $InstallRoot) | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ScriptRoot "logs") | Out-Null
$env:TEMP = $InstallerTemp
$env:TMP = $InstallerTemp

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

if (-not (Test-Path $InstallerPath)) {
    Write-Host "Downloading PostgreSQL installer..."
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerPath -UseBasicParsing
}

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "Installing PostgreSQL 16..."
    $args = @(
        "--mode", "unattended",
        "--unattendedmodeui", "none",
        "--prefix", $InstallRoot,
        "--datadir", $DataDir,
        "--serverport", $Port,
        "--servicename", $ServiceName,
        "--serviceaccount", "$env:COMPUTERNAME\administrator",
        "--servicepassword", $AdminPassword,
        "--superaccount", "postgres",
        "--superpassword", $AdminPassword,
        "--disable-components", "pgAdmin,stackbuilder",
        "--install_runtimes", "1"
    )
    $process = Start-Process -FilePath $InstallerPath -ArgumentList $args -Wait -PassThru -WindowStyle Hidden -WorkingDirectory $InstallerTemp
    if ($process.ExitCode -ne 0) {
        throw "PostgreSQL installer failed with exit code $($process.ExitCode)"
    }
}

Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline) {
    $ready = & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ready.Trim() -eq "1") {
        break
    }
    Start-Sleep -Seconds 2
}
if (-not (Test-Path $PsqlPath)) {
    throw "psql.exe not found at $PsqlPath"
}
$env:PGPASSWORD = $AdminPassword

$dbExists = & $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DatabaseName'"
if ($dbExists.Trim() -ne "1") {
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

$schemaSql = @"
GRANT CREATE, USAGE ON SCHEMA public TO $AppUser;
"@
& $PsqlPath -h 127.0.0.1 -p $Port -U postgres -d $DatabaseName -v ON_ERROR_STOP=1 -c $schemaSql

$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
& $Python (Join-Path $ScriptRoot "src\init_pg.py")

Write-Host "PostgreSQL is ready. Database initialized."
