$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

"CHECKED_AT`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

"PORT_8092"
$listeners = @(Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue)
if (-not $listeners) {
    "NO_LISTENER"
} else {
    foreach ($conn in $listeners) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine
        "PID=$($conn.OwningProcess)`tNAME=$($proc.ProcessName)`tPATH=$($proc.Path)"
        "CMD=$cmd"
    }
}

"HTTP_8092"
try {
    $res = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8092/api/ollama/status" -TimeoutSec 5
    "OK`t$($res.StatusCode)`tLEN=$($res.Content.Length)"
} catch {
    "FAIL`t$($_.Exception.Message)"
}

"PROCESSES_8092"
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "ollama_proxy_server.py|run_proxy_8092|BF_PUBLIC_PORT=8092" } |
    Select-Object ProcessId, CommandLine |
    Format-List

"LOG_PROXY_8092"
$proxyLog = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.task.log"
if (Test-Path $proxyLog) {
    Get-Item $proxyLog | Select-Object FullName, Length, LastWriteTime | Format-List
    Get-Content -LiteralPath $proxyLog -Tail 100
} else {
    "NO_LOG $proxyLog"
}

"SCRIPT_8092"
$runScript = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\run_proxy_8092.ps1"
if (Test-Path $runScript) {
    Get-Item $runScript | Select-Object FullName, Length, LastWriteTime | Format-List
    Get-Content -LiteralPath $runScript -TotalCount 160
} else {
    "NO_SCRIPT $runScript"
}
