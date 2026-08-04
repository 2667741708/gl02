$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"

$projectRoot = "F:\高炉炼铁项目-real-sensor-v2_V3"
$frontendDir = Join-Path $projectRoot "高炉前端数据"
$runScript = Join-Path $frontendDir "run_proxy_8092.ps1"
$toolsDir = Join-Path $projectRoot "tools"
$foreverScript = Join-Path $toolsDir "run_proxy_8092_forever.ps1"
$logPath = Join-Path $frontendDir "logs\proxy_8092.task.log"

if (-not (Test-Path -LiteralPath $runScript)) {
    throw "8092 run script not found: $runScript"
}
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

$foreverContent = @'
$ErrorActionPreference = "Continue"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$RunScript = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\run_proxy_8092.ps1"
$LogDir = "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\logs"
$GuardLog = Join-Path $LogDir "proxy_8092.guard.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

while ($true) {
    $started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $GuardLog -Encoding UTF8 -Value "$started starting run_proxy_8092.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RunScript
    $exit = $LASTEXITCODE
    $ended = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $GuardLog -Encoding UTF8 -Value "$ended run_proxy_8092.ps1 exited with $exit; restarting in 5s"
    Start-Sleep -Seconds 5
}
'@
Set-Content -LiteralPath $foreverScript -Encoding UTF8 -Value $foreverContent

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

function Stop-PortOwner {
    param([int]$Port)
    $owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($ownerPid in $owners) {
        if ($ownerPid -and $ownerPid -ne $PID) {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
            "STOP_PORT`t$Port`tPID=$ownerPid`t$($proc.CommandLine)"
            Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
        }
    }
}

function Show-Port {
    param([int]$Port)
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners) {
        "PORT`t$Port`tNO_LISTENER"
        return
    }
    foreach ($conn in $listeners) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
        "PORT`t$Port`tPID=$($conn.OwningProcess)`t$($proc.CommandLine)"
    }
}

"STARTED_AT`t$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
"TARGET`t$runScript"

Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -match [regex]::Escape("F:\高炉炼铁项目-real-sensor-v2_V3\tools\run_proxy_8092_forever.ps1") -or
            $_.CommandLine -match [regex]::Escape("F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据\run_proxy_8092.ps1") -or
            ($_.CommandLine -match [regex]::Escape("F:\高炉炼铁项目-real-sensor-v2_V3") -and $_.CommandLine -match "ollama_proxy_server\.py")
        )
    } |
    ForEach-Object {
        if ($_.ProcessId -ne $PID) {
            "STOP_PROXY_PROCESS`tPID=$($_.ProcessId)`t$($_.CommandLine)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

Stop-PortOwner -Port 8092
Start-Sleep -Seconds 1

$taskPath = "\BlastFurnaceServices\"
$taskName = "BaselineProxy8092"

try {
    $existing = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    if ($existing.State -eq "Running") {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {
    # Task does not exist yet.
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $foreverScript) `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount

Register-ScheduledTask `
    -TaskPath $taskPath `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Baseline blast furnace dashboard proxy on port 8092." `
    -Force | Out-Null

Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName

$ok = $false
for ($i = 1; $i -le 10; $i++) {
    Start-Sleep -Seconds 1
    $listeners = @(Get-NetTCPConnection -LocalPort 8092 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners) {
        try {
            $res = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8092/api/ollama/status" -TimeoutSec 4
            "HTTP_OK`t$($res.StatusCode)`tLEN=$($res.Content.Length)"
            $ok = $true
            break
        } catch {
            "HTTP_WAIT`t$i`t$($_.Exception.Message)"
        }
    } else {
        "LISTEN_WAIT`t$i"
    }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
"TASK`t$taskPath$taskName`tstate=$($task.State)`tlast=$($info.LastTaskResult)`tnext=$($info.NextRunTime)"
Show-Port -Port 8092

if (Test-Path -LiteralPath $logPath) {
    "LOG_TAIL"
    Get-Content -LiteralPath $logPath -Tail 60
}

$guardLog = Join-Path $frontendDir "logs\proxy_8092.guard.log"
if (Test-Path -LiteralPath $guardLog) {
    "GUARD_LOG_TAIL"
    Get-Content -LiteralPath $guardLog -Tail 20
}

if (-not $ok) {
    throw "8092 did not become healthy within short startup window"
}
