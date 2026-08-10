$root=(Get-ChildItem -LiteralPath 'F:\' -Directory|Where-Object{$_.Name-match'V4_8093_PREVIEW'}|Select-Object -First 1).FullName
$status=Join-Path $root 'logs\cooling_90d_daily_backfill_20260809.status.json'
if(-not(Test-Path -LiteralPath $status)){throw '90d status not found'}
$state=Get-Content -LiteralPath $status -Encoding UTF8 -Raw|ConvertFrom-Json
[pscustomobject]@{current_day=$state.current_day;completed_count=@($state.completed_days).Count;failed_count=@($state.failed_days).Count;backfill_complete=$state.backfill_complete;updated_at=$state.updated_at;error=$state.error}|ConvertTo-Json -Depth 4
