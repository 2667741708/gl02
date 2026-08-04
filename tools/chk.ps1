[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

Write-Output "===CHECK_TIME==="
Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Output "===PORT_8092==="
$p8092 = Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue
if ($p8092) { Write-Output "LISTEN OK"; $p8092 | Select LocalAddress,LocalPort,OwningProcess | ft -AutoSize }
else { Write-Output "NO_8092_LISTENER" }

Write-Output "===PORT_8767==="
$p8767 = Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue
if ($p8767) { Write-Output "LISTEN OK"; $p8767 | Select LocalAddress,LocalPort,OwningProcess | ft -AutoSize }
else { Write-Output "NO_8767_LISTENER" }

Write-Output "===PORT_8766==="
$p8766 = Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
if ($p8766) { Write-Output "LISTEN OK"; $p8766 | Select LocalAddress,LocalPort,OwningProcess | ft -AutoSize }
else { Write-Output "NO_8766_LISTENER" }

Write-Output "===PYTHON_PROCS==="
Get-Process -Name python -ErrorAction SilentlyContinue | Select Id, StartTime | ft -AutoSize

Write-Output "===PYTHON_CMDLINES==="
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object { Write-Output $_.CommandLine }

Write-Output "===OLLAMA_VER==="
try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 5 -UseBasicParsing; Write-Output $r.Content } catch { Write-Output "OLLAMA_FAIL" }

Write-Output "===OLLAMA_TAGS==="
try { $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -UseBasicParsing; Write-Output $r.Content } catch { Write-Output "OLLAMA_TAGS_FAIL" }

Write-Output "===SQLITE_DB==="
$dbPath = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\data\bf_qa.sqlite3"
if (Test-Path $dbPath) {
    $item = Get-Item $dbPath
    Write-Output "DB_EXISTS Size=$($item.Length) LastWrite=$($item.LastWriteTime)"
} else { Write-Output "DB_NOT_FOUND" }

Write-Output "===PG_PORT==="
if (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue) { Write-Output "PG_LISTENING" }
else { Write-Output "PG_NOT_LISTENING" }

Write-Output "===PROXY_TASK_LOG==="
$taskLog = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.task.log"
if (Test-Path $taskLog) { Get-Content $taskLog -Tail 30 -Encoding UTF8 } else { Write-Output "NOT_FOUND" }

Write-Output "===GUARD_LOG==="
$guardLog = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.guard.log"
if (Test-Path $guardLog) { Get-Content $guardLog -Tail 20 -Encoding UTF8 } else { Write-Output "NOT_FOUND" }

Write-Output "===WMI_OUT_LOG==="
$wmiOut = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.wmi.out.log"
if (Test-Path $wmiOut) {
    Write-Output "SIZE=$((Get-Item $wmiOut).Length)"
    Get-Content $wmiOut -Tail 20 -Encoding UTF8
} else { Write-Output "NOT_FOUND" }

Write-Output "===WMI_ERR_LOG==="
$wmiErr = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs\proxy_8092.wmi.err.log"
if (Test-Path $wmiErr) {
    Write-Output "SIZE=$((Get-Item $wmiErr).Length)"
    Get-Content $wmiErr -Tail 20 -Encoding UTF8
} else { Write-Output "NOT_FOUND" }

Write-Output "===SCHEDULED_TASKS==="
Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -ErrorAction SilentlyContinue | Select TaskName, State | ft -AutoSize
Get-ScheduledTask -TaskName "BlastFurnaceV3Proxy8092" -ErrorAction SilentlyContinue | Select TaskName, State | ft -AutoSize
Get-ScheduledTask -TaskPath "\GL02SensorSync\" -ErrorAction SilentlyContinue | Select TaskName, State | ft -AutoSize

Write-Output "===DONE==="
