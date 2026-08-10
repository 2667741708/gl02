$pidFile='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.pid'
$stdout='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.out.log'
$stderr='C:\Users\Administrator\AppData\Local\Temp\cooling_backfill_then_baseline.err.log'
$root=Get-ChildItem -LiteralPath 'F:\' -Directory | Where-Object {$_.Name -match 'V4_8093_PREVIEW'} | Select-Object -First 1
$status=if($root){Join-Path $root.FullName 'logs\cooling_backfill_baseline_20260809.status.json'}else{$null}
$workerPid=[int](Get-Content -LiteralPath $pidFile -Encoding ASCII)
$running=$null-ne(Get-Process -Id $workerPid -ErrorAction SilentlyContinue)
$outTail=if(Test-Path -LiteralPath $stdout){Get-Content -LiteralPath $stdout -Encoding UTF8 -Tail 15|ForEach-Object{$_.ToString()}}else{@()}
$errTail=if(Test-Path -LiteralPath $stderr){Get-Content -LiteralPath $stderr -Encoding UTF8 -Tail 15|ForEach-Object{$_.ToString()}}else{@()}
$statusText=if($status -and (Test-Path -LiteralPath $status)){Get-Content -LiteralPath $status -Encoding UTF8 -Raw}else{$null}
[pscustomobject]@{pid=$workerPid;running=$running;status=$statusText;stdout_tail=@($outTail);stderr_tail=@($errTail)}|ConvertTo-Json -Depth 5
