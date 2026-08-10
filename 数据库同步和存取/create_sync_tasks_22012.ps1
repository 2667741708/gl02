$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$HistoryScript = Join-Path $ScriptRoot "run_history_sync_pg_bg.ps1"
$RealtimeScript = Join-Path $ScriptRoot "run_realtime_sync_pg_bg.ps1"
$TaskFolder = "\GL02SensorSync"
$HistoryTask = "$TaskFolder\History90d"
$RealtimeTask = "$TaskFolder\Realtime"
$StartTime = (Get-Date).AddMinutes(1).ToString("HH:mm")

$HistoryCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$HistoryScript`""
$RealtimeCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$RealtimeScript`""

schtasks.exe /Create /TN $HistoryTask /SC ONCE /ST $StartTime /TR $HistoryCommand /RU SYSTEM /RL HIGHEST /F | Out-Host
schtasks.exe /Create /TN $RealtimeTask /SC ONSTART /TR $RealtimeCommand /RU SYSTEM /RL HIGHEST /F | Out-Host
schtasks.exe /Run /TN $HistoryTask | Out-Host
schtasks.exe /Run /TN $RealtimeTask | Out-Host

[PSCustomObject]@{
    history_task = $HistoryTask
    realtime_task = $RealtimeTask
    history_script = $HistoryScript
    realtime_script = $RealtimeScript
} | ConvertTo-Json -Depth 3
