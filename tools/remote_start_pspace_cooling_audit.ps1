$ErrorActionPreference = 'Stop'
$python = 'C:\Program Files\Python311\python.exe'
$script = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.py'
$stdout = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.json'
$stderr = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.err.log'
$pidFile = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.pid'
$process = Start-Process -FilePath $python -ArgumentList @($script) -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
Write-Output ('AUDIT_PID=' + $process.Id)
