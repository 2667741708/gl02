$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$paths = @(
    (Join-Path $root "db_dashboard\\server.py"),
    (Join-Path $root "db_dashboard\\heat.html"),
    (Join-Path $root "高炉前端数据\\libs\\echarts.min.js"),
    "F:\\高炉炼铁项目-real-sensor-v2_V3\\db_dashboard\\server.py",
    "F:\\高炉炼铁项目-real-sensor-v2_V3\\db_dashboard\\heat.html"
)
$listeners = @{}
foreach ($port in 8890, 8891, 5432, 15432, 15433, 18080, 18889, 8094) {
    $listeners[[string]$port] = @(
        Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -First 3 -Property LocalAddress,LocalPort,OwningProcess
    )
}
$checks = foreach ($path in $paths) {
    [ordered]@{ path = $path; exists = Test-Path -LiteralPath $path }
}
[ordered]@{
    root = $root
    paths = $checks
    listeners = $listeners
    python311 = Test-Path -LiteralPath "C:\\Program Files\\Python311\\python.exe"
    python311_version = if (Test-Path -LiteralPath "C:\\Program Files\\Python311\\python.exe") {
        & "C:\\Program Files\\Python311\\python.exe" --version 2>&1 | Out-String
    } else { "" }
    python_modules = if (Test-Path -LiteralPath "C:\\Program Files\\Python311\\python.exe") {
        & "C:\\Program Files\\Python311\\python.exe" -c "import importlib.util; print({'psycopg':bool(importlib.util.find_spec('psycopg')), 'openpyxl':bool(importlib.util.find_spec('openpyxl'))})" 2>&1 | Out-String
    } else { "" }
    db_env_presence = [ordered]@{
        GL02_PGHOST = [bool](Get-Item Env:GL02_PGHOST -ErrorAction SilentlyContinue)
        GL02_PGPORT = [bool](Get-Item Env:GL02_PGPORT -ErrorAction SilentlyContinue)
        GL02_PGDATABASE = [bool](Get-Item Env:GL02_PGDATABASE -ErrorAction SilentlyContinue)
        GL02_PGUSER = [bool](Get-Item Env:GL02_PGUSER -ErrorAction SilentlyContinue)
        GL02_PGPASSWORD = [bool](Get-Item Env:GL02_PGPASSWORD -ErrorAction SilentlyContinue)
    }
} | ConvertTo-Json -Depth 6
