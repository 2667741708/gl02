$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
$log = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\logs\heat_performance_quality_sync.log'
$envPresence = @{}
foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $envPresence[$name] = [bool][Environment]::GetEnvironmentVariable($name, 'Machine')
}
$events = @()
try {
    $events = @(Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' -MaxEvents 100 | Where-Object {
        $_.Message -match 'HeatPerformanceQualitySync'
    } | Select-Object -First 12 TimeCreated, Id, LevelDisplayName, Message)
} catch {
    $events = @([pscustomobject]@{ error = $_.Exception.Message })
}

[ordered]@{
    state = $task.State.ToString()
    principal = $task.Principal | Select-Object UserId, LogonType, RunLevel
    action = $task.Actions | Select-Object Execute, Arguments, WorkingDirectory
    last_run_time = $info.LastRunTime.ToString('o')
    last_task_result = $info.LastTaskResult
    next_run_time = $info.NextRunTime.ToString('o')
    log = if (Test-Path -LiteralPath $log) {
        Get-Item -LiteralPath $log | Select-Object FullName, Length, LastWriteTime
    } else { $null }
    machine_environment_present = $envPresence
    task_events = $events
} | ConvertTo-Json -Depth 8
