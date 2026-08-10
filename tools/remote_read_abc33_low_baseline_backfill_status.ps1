$ErrorActionPreference='Stop'
$root=(Get-ChildItem -LiteralPath 'F:\' -Directory|Where-Object{$_.Name-match'V4_8093_PREVIEW'}|Select-Object -First 1).FullName
$status=Join-Path $root 'logs\abc33_low_baseline_30d_backfill_20260809.status.json'
$processes=Get-CimInstance Win32_Process|Where-Object{$_.CommandLine-match'remote_run_abc33_low_baseline_30d_backfill'}|Select-Object ProcessId,Name
$state=if(Test-Path -LiteralPath $status){Get-Content -LiteralPath $status -Raw|ConvertFrom-Json}else{$null}
[pscustomobject]@{processes=@($processes);state=$state}|ConvertTo-Json -Depth 8
