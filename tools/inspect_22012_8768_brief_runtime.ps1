$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"
chcp 65001 > $null

function Section($name) {
    Write-Host ""
    Write-Host "===== $name ====="
}

$v4 = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$logs = Join-Path $v4 "logs"

Section "NOW_AND_BOOT"
[pscustomobject]@{
    Now = Get-Date
    ComputerName = $env:COMPUTERNAME
    User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    LastBootUpTime = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
} | Format-List

Section "TASK_V4PREVIEW_WS8768"
$task = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V4PreviewWs8768" -ErrorAction SilentlyContinue
$info = Get-ScheduledTaskInfo -TaskPath "\BlastFurnaceServices\" -TaskName "V4PreviewWs8768" -ErrorAction SilentlyContinue
if ($task) {
    [pscustomobject]@{
        State = $task.State
        Enabled = $task.Settings.Enabled
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
        NextRunTime = $info.NextRunTime
        NumberOfMissedRuns = $info.NumberOfMissedRuns
        ExecutionTimeLimit = $task.Settings.ExecutionTimeLimit
        RestartCount = $task.Settings.RestartCount
        RestartInterval = $task.Settings.RestartInterval
        StartWhenAvailable = $task.Settings.StartWhenAvailable
        Action = ($task.Actions | ForEach-Object { ($_.Execute + " " + $_.Arguments).Trim() }) -join " || "
    } | Format-List
} else {
    "TASK_NOT_FOUND"
}

Section "LISTEN_PORTS"
Get-NetTCPConnection -LocalPort 8093,8767,8768 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize

Section "PROCESS_8768"
Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%8768%'" -ErrorAction SilentlyContinue |
    Select-Object ProcessId, Name, CreationDate, CommandLine |
    Format-List

Section "LOG_META"
foreach ($fileName in @("ws_8768.guard.log", "ws_8768.out.log", "ws_8768.err.log")) {
    $path = Join-Path $logs $fileName
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path
        [pscustomobject]@{
            Name = $fileName
            Length = $item.Length
            CreationTime = $item.CreationTime
            LastWriteTime = $item.LastWriteTime
            LastLine = (Get-Content -LiteralPath $path -Tail 1 -Encoding UTF8 -ErrorAction SilentlyContinue)
        } | Format-List
    } else {
        [pscustomobject]@{ Name = $fileName; Exists = $false } | Format-List
    }
}

Section "GUARD_LOG_ALL"
$guard = Join-Path $logs "ws_8768.guard.log"
if (Test-Path -LiteralPath $guard) {
    Get-Content -LiteralPath $guard -Encoding UTF8
}

Section "RUNNER_FILES"
foreach ($path in @(
    "$v4\tools\run_v4_8768_ws_forever.ps1",
    "$v4\tools\run_v4_8768_ws_once.ps1",
    "$v4\tools\start_v3_ws_bridge_python.py",
    "$v4\自动诊断服务\local_pg_ws_bridge.py"
)) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path
        [pscustomobject]@{ Path = $path; Exists = $true; Length = $item.Length; LastWriteTime = $item.LastWriteTime } | Format-List
    } else {
        [pscustomobject]@{ Path = $path; Exists = $false } | Format-List
    }
}

Section "FIREWALL_8768"
Get-NetFirewallRule -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match "8768|V4 Preview" } |
    Select-Object DisplayName, Enabled, Direction, Action, Profile |
    Format-Table -AutoSize
