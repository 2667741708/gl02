$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$pattern = '(?i)(si[_ -]?v20|predict.*si|si.*predict|hourly.*si|si.*hourly|hourly-predict)'
$matches = foreach ($task in Get-ScheduledTask) {
    $actionText = @($task.Actions | ForEach-Object {
        "{0} {1}" -f $_.Execute, $_.Arguments
    }) -join ' '
    if ($task.TaskName -match $pattern -or $actionText -match $pattern) {
        [pscustomobject]@{
            TaskPath = $task.TaskPath
            TaskName = $task.TaskName
            State = $task.State.ToString()
            Actions = $actionText
        }
    }
}

@{
    schema = 'ops.si-v20.hourly-task-audit.v1'
    audited_at = (Get-Date).ToString('o')
    count = @($matches).Count
    tasks = @($matches)
} | ConvertTo-Json -Depth 5
