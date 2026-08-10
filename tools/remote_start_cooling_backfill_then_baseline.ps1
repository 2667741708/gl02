$ErrorActionPreference='Stop'
$worker='C:\Users\Administrator\AppData\Local\Temp\remote_run_cooling_backfill_then_baseline.ps1'
$stdout='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.out.log'
$stderr='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.err.log'
$pidFile='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.pid'
$process=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$worker) -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
Write-Output ('WORKER_PID='+$process.Id)
