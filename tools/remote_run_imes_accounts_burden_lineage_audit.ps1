$env:IMES_OPS_DB_HOST = "10.10.181.195"
$env:IMES_OPS_DB_PORT = "5432"
$env:IMES_LAB_DB_HOST = "10.10.181.195"
$env:IMES_LAB_DB_PORT = "5432"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

& "C:\Program Files\Python311\python.exe" -X utf8 ".\tools\audit_imes_accounts_and_burden_lineage.py"
exit $LASTEXITCODE
