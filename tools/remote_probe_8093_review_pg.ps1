$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$python = 'C:\Program Files\Python311\python.exe'
$probe = 'C:\Users\Administrator\AppData\Local\Temp\bf_diag_db_probe.py'
foreach ($required in @($python, $probe)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "required privilege probe input is missing: $required"
    }
}

$hostName = [Environment]::GetEnvironmentVariable('GL02_PGHOST', 'Machine')
$port = [Environment]::GetEnvironmentVariable('GL02_PGPORT', 'Machine')
$database = [Environment]::GetEnvironmentVariable('GL02_PGDATABASE', 'Machine')
$userName = [Environment]::GetEnvironmentVariable('GL02_PGUSER', 'Machine')
$password = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD', 'Machine')
if ([string]::IsNullOrWhiteSpace($hostName)) { $hostName = '127.0.0.1' }
if ([string]::IsNullOrWhiteSpace($port)) { $port = '5432' }
if ([string]::IsNullOrWhiteSpace($database)) { $database = 'bf_trend' }
if ([string]::IsNullOrWhiteSpace($userName) -or [string]::IsNullOrWhiteSpace($password)) {
    throw 'GL02 PostgreSQL machine credentials are not configured'
}

$env:GL02_PGHOST = $hostName
$env:GL02_PGPORT = $port
$env:GL02_PGDATABASE = $database
$env:GL02_PGUSER = $userName
$env:GL02_PGPASSWORD = $password
try {
    & $python -X utf8 $probe
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL privilege probe failed with exit code $LASTEXITCODE"
    }
}
finally {
    foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    }
}
