$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_foreman_trend_8892"
$server = "$root\tools\foreman_trend_server.py"
$frontendDir = "$root\高炉前端数据"
$logDir = "$root\logs"
$log = "$logDir\foreman_trend_8892.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

# Reuse machine-scoped GL02 read-only connection
foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:BF_FOREMAN_HOST = "0.0.0.0"
$env:BF_FOREMAN_PORT = "8892"
$env:BF_FRONTEND_DIR = $frontendDir

if (-not (Test-Path -LiteralPath $server)) {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') missing server: $server"
    exit 2
}

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting foreman trend on 8892"
    Set-Location -LiteralPath $root
    & "C:\Program Files\Python311\python.exe" -X utf8 -u $server >> $log 2>&1
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt foreman trend exited with code $LASTEXITCODE; restart in 5s"
    Start-Sleep -Seconds 5
}
