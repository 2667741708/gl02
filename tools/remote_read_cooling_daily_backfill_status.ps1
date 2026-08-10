$root=(Get-ChildItem -LiteralPath 'F:\' -Directory|Where-Object{$_.Name-match'V4_8093_PREVIEW'}|Select-Object -First 1).FullName
$status=Join-Path $root 'logs\cooling_daily_backfill_20260809.status.json'
$log=Join-Path $root 'logs\cooling_daily_backfill_20260809.log'
[pscustomobject]@{status=(Get-Content -LiteralPath $status -Encoding UTF8 -Raw);log_tail=@(Get-Content -LiteralPath $log -Encoding UTF8 -Tail 12|ForEach-Object{$_.ToString()})}|ConvertTo-Json -Depth 5
