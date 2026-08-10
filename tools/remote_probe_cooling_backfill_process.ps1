$items=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'sync_from_243_pg.py' -and $_.CommandLine -match 'Q_soft_water'} | Select-Object ProcessId,ParentProcessId,CreationDate,Name,CommandLine
[pscustomobject]@{checked_at=Get-Date;processes=@($items)}|ConvertTo-Json -Depth 4
