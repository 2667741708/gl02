$ErrorActionPreference = "Stop"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8095"
Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Start-Sleep -Seconds 8
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$info = Get-ScheduledTaskInfo -InputObject $task
$listener = Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
[ordered]@{
    task_state = $task.State.ToString()
    last_task_result = $info.LastTaskResult
    listener = if ($listener) { [ordered]@{ address = $listener.LocalAddress; port = $listener.LocalPort; pid = $listener.OwningProcess } } else { $null }
} | ConvertTo-Json -Depth 5
