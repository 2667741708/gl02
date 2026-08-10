$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$entry = Join-Path $projectRoot '数据库同步和存取\run_22012_bf2_operation_log_report_sync.ps1'
$taskName = 'IMESBF2OperationLogReport5m'

$result = [ordered]@{
    entry_exists = Test-Path -LiteralPath $entry
    entry = $entry
    task = $null
    task_info = $null
    script_refs = @()
    entry_head = @()
}

if ($result.entry_exists) {
    $result.entry_head = Get-Content -LiteralPath $entry -TotalCount 80 -Encoding UTF8
    $result.script_refs = Select-String -LiteralPath $entry -Pattern '\.py|\.sql|operation_log|report|imes' -Encoding UTF8 | Select-Object LineNumber, Line
}

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    $result.task = $task | Select-Object TaskName, State, TaskPath
    $result.task_info = Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
}

$result | ConvertTo-Json -Depth 6
