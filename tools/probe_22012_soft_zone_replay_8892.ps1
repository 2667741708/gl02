$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$TaskPath = '\BlastFurnaceServices\'
$TaskName = 'SoftZoneTemperatureReplay8892'
$LogFile = Join-Path $ProjectRoot 'logs\soft_zone_replay_8892.log'
$Server = Join-Path $ProjectRoot 'tools\soft_zone_replay_server.py'
$Static = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\index.html'

$task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
$taskInfo = $null
if ($task) {
    $taskInfo = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName
}

$logTail = @()
if (Test-Path -LiteralPath $LogFile) {
    $logTail = @(Get-Content -LiteralPath $LogFile -Tail 80 | ForEach-Object { [string]$_ })
}

[pscustomobject]@{
    listener = @(netstat -ano -p TCP | Select-String -Pattern '^\s*TCP\s+\S+:8892\s+\S+\s+LISTENING\s+\d+\s*$' | ForEach-Object { $_.Line.Trim() })
    task_exists = [bool]$task
    task_state = if ($task) { [string]$task.State } else { $null }
    last_task_result = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
    server_exists = Test-Path -LiteralPath $Server
    static_exists = Test-Path -LiteralPath $Static
    log_exists = Test-Path -LiteralPath $LogFile
    log_tail = $logTail
} | ConvertTo-Json -Depth 5
