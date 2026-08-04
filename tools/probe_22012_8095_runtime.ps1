$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8095"
$taskInfo = Get-ScheduledTaskInfo -InputObject $task
$connection = Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$process = if ($connection) { Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" } else { $null }
$parent = if ($process) { Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue } else { $null }
[ordered]@{
    port = if ($connection) { $connection.LocalPort } else { $null }
    address = if ($connection) { $connection.LocalAddress } else { $null }
    process_id = if ($process) { $process.ProcessId } else { $null }
    command_line = if ($process) { $process.CommandLine } else { $null }
    parent_id = if ($process) { $process.ParentProcessId } else { $null }
    parent_command_line = if ($parent) { $parent.CommandLine } else { $null }
    task_state = $task.State.ToString()
    task_last_result = $taskInfo.LastTaskResult
    task_action = @($task.Actions | ForEach-Object { $_.Execute + " " + $_.Arguments })
    runner_exists = Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8095_preview.ps1"
    backend_exists = Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server_8095.py"
    page_exists = Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.8095_preview.server.html"
    log_tail = if (Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\preview_proxy_8095.log") { Get-Content -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\preview_proxy_8095.log" -Tail 40 } else { @() }
} | ConvertTo-Json -Depth 5
