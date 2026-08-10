$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$env:IMES_OPS_DB_HOST = '10.10.181.195'
$env:IMES_OPS_DB_PORT = '5432'
$env:IMES_LAB_DB_HOST = '10.10.181.195'
$env:IMES_LAB_DB_PORT = '5432'
$env:PYTHONUTF8 = '1'

& 'C:\Program Files\Python311\python.exe' -X utf8 '.\tools\remote_probe_vastbase_20260806_089_090.py'
exit $LASTEXITCODE
