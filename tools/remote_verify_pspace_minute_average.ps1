$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$verifyScript = 'C:\Users\Administrator\AppData\Local\Temp\verify_22012_pspace_minute_average.py'

foreach ($name in 'GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD') {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, 'User') }
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'C:\Program Files\Python311\python.exe' }

& $python -X utf8 $verifyScript --project-root $projectRoot
if ($LASTEXITCODE -ne 0) {
    throw "minute-average verification failed with exit code $LASTEXITCODE"
}
