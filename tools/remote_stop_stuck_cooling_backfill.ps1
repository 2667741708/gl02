$ErrorActionPreference='Stop'
$matches=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'sync_from_243_pg.py' -and $_.CommandLine -match '--days 35' -and $_.CommandLine -match 'Q_soft_water'}
if(@($matches).Count-ne 1){throw ('Expected exactly one matching process, found '+@($matches).Count)}
$target=$matches|Select-Object -First 1
Stop-Process -Id $target.ProcessId -Force
Start-Sleep -Seconds 1
if(Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue){throw 'Cooling backfill process did not stop'}
Write-Output ('STOPPED_PID='+$target.ProcessId)
