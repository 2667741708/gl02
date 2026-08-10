$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$env:IMES_OPS_DB_HOST = '10.10.181.195'
$env:IMES_OPS_DB_PORT = '5432'
$env:IMES_LAB_DB_HOST = '10.10.181.195'
$env:IMES_LAB_DB_PORT = '5432'
$env:PYTHONUTF8 = '1'

& 'C:\Program Files\Python311\python.exe' -m py_compile '.\tools\sync_22012_heat_performance_quality.py'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& 'C:\Program Files\Python311\python.exe' -X utf8 '.\tools\sync_22012_heat_performance_quality.py' --since-days 3 --repair-days 3
exit $LASTEXITCODE
