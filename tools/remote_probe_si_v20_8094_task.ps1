$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V3AutoPreviewProxy8094' -ErrorAction Stop
[ordered]@{
    state = [string]$task.State
    actions = @($task.Actions | ForEach-Object {
        [ordered]@{ execute = $_.Execute; arguments = $_.Arguments; working_directory = $_.WorkingDirectory }
    })
} | ConvertTo-Json -Depth 5
