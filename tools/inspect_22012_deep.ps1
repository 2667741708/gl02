[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

Write-Output "===CHECK_TIME==="
Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Output "===PORT_8092==="
$listeners = Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    $listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
} else {
    Write-Output "NO_LISTENER_ON_8092"
}

Write-Output "===PORT_8767==="
$wsListeners = Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue
if ($wsListeners) {
    $wsListeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
} else {
    Write-Output "NO_LISTENER_ON_8767"
}

Write-Output "===PORT_8766==="
$ws2Listeners = Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
if ($ws2Listeners) {
    $ws2Listeners | Select-Object LocalAddress, LocalPort, State, OwningProcess | Format-Table -AutoSize
} else {
    Write-Output "NO_LISTENER_ON_8766"
}

Write-Output "===PYTHON_PROCESSES_8092==="
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*ollama_proxy*" -or $_.CommandLine -like "*8092*" } | Select-Object ProcessId, CreationDate, CommandLine | Format-List

Write-Output "===GUARDIAN_PROCESSES==="
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like "*run_proxy_8092*" } | Select-Object ProcessId, CreationDate, CommandLine | Format-List

Write-Output "===TASK_LOG_TAIL==="
$taskLog = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.task.log"
if (Test-Path $taskLog) {
    Write-Output "Size: $((Get-Item $taskLog).Length) bytes"
    Get-Content $taskLog -Tail 30 -Encoding UTF8
} else {
    Write-Output "TASK_LOG_NOT_FOUND"
}

Write-Output "===GUARD_LOG_TAIL==="
$guardLog = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.guard.log"
if (Test-Path $guardLog) {
    Write-Output "Size: $((Get-Item $guardLog).Length) bytes"
    Get-Content $guardLog -Tail 20 -Encoding UTF8
} else {
    Write-Output "GUARD_LOG_NOT_FOUND"
}

Write-Output "===WMI_LOG_TAIL==="
$wmiOut = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.wmi.out.log"
$wmiErr = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.wmi.err.log"
if (Test-Path $wmiOut) {
    Write-Output "---WMI_OUT_LOG_SIZE: $((Get-Item $wmiOut).Length) bytes---"
    Get-Content $wmiOut -Tail 30 -Encoding UTF8
} else { Write-Output "WMI_OUT_LOG_NOT_FOUND" }
if (Test-Path $wmiErr) {
    Write-Output "---WMI_ERR_LOG_SIZE: $((Get-Item $wmiErr).Length) bytes---"
    Get-Content $wmiErr -Tail 30 -Encoding UTF8
} else { Write-Output "WMI_ERR_LOG_NOT_FOUND" }

Write-Output "===OLLAMA_VERSION==="
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 5 -UseBasicParsing
    Write-Output $r.Content
} catch {
    Write-Output "OLLAMA_VERSION_FAIL"
}

Write-Output "===OLLAMA_TAGS==="
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -UseBasicParsing
    Write-Output $r.Content
} catch {
    Write-Output "OLLAMA_TAGS_FAIL"
}

Write-Output "===SQLITE_DB==="
$dbPath = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\data\bf_qa.sqlite3"
if (Test-Path $dbPath) {
    Write-Output "DB_EXISTS; Size: $((Get-Item $dbPath).Length) bytes; LastWrite: $((Get-Item $dbPath).LastWriteTime)"
} else {
    Write-Output "DB_NOT_FOUND"
}

Write-Output "===POSTGRESQL_PORT==="
$pgListeners = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
if ($pgListeners) {
    Write-Output "PG_LISTENING"
} else {
    Write-Output "PG_NOT_LISTENING"
}

Write-Output "===SCHEDULED_TASKS==="
Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -ErrorAction SilentlyContinue | Select-Object TaskName, State | Format-Table -AutoSize
Get-ScheduledTask -TaskName "BlastFurnaceV3Proxy8092" -ErrorAction SilentlyContinue | Select-Object TaskName, State | Format-Table -AutoSize
Get-ScheduledTask -TaskPath "\GL02SensorSync\" -ErrorAction SilentlyContinue | Select-Object TaskName, State | Format-Table -AutoSize

Write-Output "===DONE==="
