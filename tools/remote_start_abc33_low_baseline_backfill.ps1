$ErrorActionPreference='Stop'
$script='C:\Users\Administrator\AppData\Local\Temp\remote_run_abc33_low_baseline_30d_backfill.ps1'
if(-not(Test-Path -LiteralPath $script)){throw 'Staged ABC33 backfill script not found'}
$existing=Get-CimInstance Win32_Process|Where-Object{$_.CommandLine-match'abc33_low_baseline_30d_backfill'}
if($existing){$existing|Select-Object ProcessId,Name,CommandLine|ConvertTo-Json -Depth 3;exit 0}
$process=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script) -WindowStyle Hidden -PassThru
[pscustomobject]@{ok=$true;pid=$process.Id;script=$script}|ConvertTo-Json
