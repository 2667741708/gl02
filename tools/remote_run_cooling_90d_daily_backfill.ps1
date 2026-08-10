$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root=(Get-ChildItem -LiteralPath 'F:\' -Directory|Where-Object{$_.Name-match'V4_8093_PREVIEW'}|Select-Object -First 1).FullName
if(-not $root){throw 'V4 root not found'}
$syncFile=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_from_243_pg.py' -File -ErrorAction SilentlyContinue|Where-Object{$_.FullName-match'V4_8093_PREVIEW'-and$_.FullName-notmatch'\\backups\\'}|Select-Object -First 1
$configFile=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_config.json' -File -ErrorAction SilentlyContinue|Where-Object{$_.FullName-match'V4_8093_PREVIEW'-and$_.FullName-notmatch'\\backups\\'}|Select-Object -First 1
if(-not $syncFile-or-not $configFile){throw 'Sync runtime not found'}
$python='C:\Program Files\Python311\python.exe'
$log=Join-Path $root 'logs\cooling_90d_daily_backfill_20260809.log'
$statusPath=Join-Path $root 'logs\cooling_90d_daily_backfill_20260809.status.json'
$start=(Get-Date).Date.AddDays(-90)
$end=(Get-Date).Date
$state=[ordered]@{schema='ops.cooling-90d-daily-backfill.v1';started_at=Get-Date;window_start=$start;window_end_exclusive=$end;current_day=$null;completed_days=@();failed_days=@();backfill_complete=$false;updated_at=Get-Date;error=$null}
function Save-State{$state.updated_at=Get-Date;$state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $statusPath -Encoding UTF8}
Save-State
try{
  $day=$start
  while($day-lt$end){
    $next=$day.AddDays(1)
    $label=$day.ToString('yyyy-MM-dd')
    $state.current_day=$label
    Save-State
    $ok=$false
    for($attempt=1;$attempt-le3-and-not$ok;$attempt++){
      Add-Content -LiteralPath $log -Encoding UTF8 -Value ('DAY_START '+$label+' attempt='+$attempt+' at='+(Get-Date).ToString('o'))
      $arguments=@('-X','utf8',$syncFile.FullName,'--config',$configFile.FullName,'--start-time',$day.ToString('yyyy-MM-dd HH:mm:ss'),'--end-time',$next.ToString('yyyy-MM-dd HH:mm:ss'),'--chunk-hours','4','--batch-size','3','--max-workers','1','--retries','2','--retry-sleep','5','--source-mode','raw','--source-interval-seconds','5','--source-aggregate','average','--target-aggregate','PS_RAW_AVERAGE','--target-interval-seconds','60','--no-persist-raw-5s','--variables','Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel','--skip-retention')
      $previousPreference=$ErrorActionPreference
      $ErrorActionPreference='Continue'
      & $python @arguments 2>&1|Out-File -LiteralPath $log -Encoding UTF8 -Append
      $exitCode=$LASTEXITCODE
      $ErrorActionPreference=$previousPreference
      if($exitCode-eq0){$ok=$true;Add-Content -LiteralPath $log -Encoding UTF8 -Value ('DAY_OK '+$label+' at='+(Get-Date).ToString('o'))}
      else{Add-Content -LiteralPath $log -Encoding UTF8 -Value ('DAY_FAIL '+$label+' attempt='+$attempt+' exit='+$exitCode)}
    }
    if(-not$ok){$state.failed_days+=,$label;Save-State;throw ('Daily backfill failed: '+$label)}
    $state.completed_days+=,$label
    $day=$next
    Save-State
  }
  $state.current_day=$null
  $state.backfill_complete=$true
}catch{$state.error=$_.Exception.Message;throw}
finally{Save-State}
