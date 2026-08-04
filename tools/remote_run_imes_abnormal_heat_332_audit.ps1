$ErrorActionPreference = "Stop"
$env:IMES_OPS_DB_HOST = "10.10.181.195"
$env:IMES_OPS_DB_PORT = "5432"
$env:IMES_LAB_DB_HOST = "10.10.181.195"
$env:IMES_LAB_DB_PORT = "5432"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
Set-Location -LiteralPath $root
& "C:\Program Files\Python311\python.exe" -X utf8 ".\tools\audit_imes_abnormal_heat_332.py"
exit $LASTEXITCODE
