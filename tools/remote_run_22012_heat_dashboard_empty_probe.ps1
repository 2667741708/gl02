$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:IMES_OPS_DB_HOST = "10.10.181.195"
$env:IMES_OPS_DB_PORT = "5432"
$env:IMES_LAB_DB_HOST = "10.10.181.195"
$env:IMES_LAB_DB_PORT = "5432"

& "C:\Program Files\Python311\python.exe" -X utf8 `
    "$root\tools\probe_22012_heat_dashboard_empty_data.py" `
    --root $root `
    --limit 24
exit $LASTEXITCODE
