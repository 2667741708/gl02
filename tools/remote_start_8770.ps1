$ErrorActionPreference = 'Stop'
Start-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V4BillboardPspace8770'
Start-Sleep -Seconds 5
$task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V4BillboardPspace8770'
$listener = netstat -ano -p tcp | Select-String ':8770\s+.*LISTENING' | Select-Object -First 1
[ordered]@{ state = [string]$task.State; listener = if ($listener) { $listener.Line } else { $null } } | ConvertTo-Json
