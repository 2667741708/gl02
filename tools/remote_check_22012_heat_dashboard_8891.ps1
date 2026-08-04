$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
$taskPath = "\BlastFurnaceServices\"
$taskName = "StandaloneHeatDashboard8891"
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    "$root\run_22012_heat_dashboard_8891.ps1",
    [ref]$tokens,
    [ref]$parseErrors
) | Out-Null
[ordered]@{
    task = if ($task) { $task | Select-Object TaskName,TaskPath,State } else { $null }
    task_info = if ($info) { $info | Select-Object LastRunTime,LastTaskResult,NumberOfMissedRuns } else { $null }
    actions = if ($task) { $task.Actions | Select-Object Execute,Arguments,WorkingDirectory } else { $null }
    triggers = if ($task) { $task.Triggers | Select-Object TriggerType,Enabled,StartBoundary } else { $null }
    runner_exists = Test-Path -LiteralPath "$root\run_22012_heat_dashboard_8891.ps1"
    server_exists = Test-Path -LiteralPath "$root\db_dashboard\server.py"
    secret_exists = Test-Path -LiteralPath "$root\PT\imes_vastbase.local.env"
    runner_parse_errors = @($parseErrors | ForEach-Object { $_.Message })
    log_exists = Test-Path -LiteralPath "$root\logs\heat_dashboard_8891.log"
    log_tail = if (Test-Path -LiteralPath "$root\logs\heat_dashboard_8891.log") { Get-Content -LiteralPath "$root\logs\heat_dashboard_8891.log" -Tail 80 } else { @() }
    listener = @(Get-NetTCPConnection -State Listen -LocalPort 8891 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
} | ConvertTo-Json -Depth 8
