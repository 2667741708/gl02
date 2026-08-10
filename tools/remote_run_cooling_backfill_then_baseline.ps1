$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$root=Get-ChildItem -LiteralPath 'F:\' -Directory | Where-Object {$_.Name -match 'V4_8093_PREVIEW'} | Select-Object -First 1
if(-not $root){throw 'V4 root not found'}
$root=$root.FullName
$python='C:\Program Files\Python311\python.exe'
$syncFile=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_from_243_pg.py' -File -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match 'V4_8093_PREVIEW' -and $_.FullName -notmatch '\\backups\\'} | Select-Object -First 1
if(-not $syncFile){throw 'sync_from_243_pg.py not found'}
$sync=$syncFile.FullName
$configFile=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_config.json' -File -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match 'V4_8093_PREVIEW' -and $_.FullName -notmatch '\\backups\\'} | Select-Object -First 1
if(-not $configFile){throw 'sync_config.json not found'}
$config=$configFile.FullName
$baseline=Join-Path $root 'tools\run_v4_daily_baseline.ps1'
$status=Join-Path $root 'logs\cooling_backfill_baseline_20260809.status.json'
$started=Get-Date
$result=[ordered]@{schema='ops.cooling-backfill-baseline.v1';started_at=$started;backfill_days=35;backfill_ok=$false;baseline_ok=$false;completed_at=$null;error=$null}
try{
  $existing=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'sync_from_243_pg.py' -and $_.CommandLine -match 'Q_soft_water'}
  if($existing){throw 'Another cooling backfill process is already running'}
  $arguments=@(
    '-X','utf8',$sync,'--config',$config,'--days','35','--chunk-hours','4','--batch-size','3','--max-workers','1',
    '--source-mode','raw','--source-interval-seconds','5','--source-aggregate','average',
    '--target-aggregate','PS_RAW_AVERAGE','--target-interval-seconds','60','--no-persist-raw-5s',
    '--variables','Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel','--skip-retention'
  )
  & $python @arguments
  if($LASTEXITCODE-ne 0){throw ('Cooling backfill failed with exit code '+$LASTEXITCODE)}
  $result.backfill_ok=$true
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $baseline
  if($LASTEXITCODE-ne 0){throw ('Baseline rebuild failed with exit code '+$LASTEXITCODE)}
  $result.baseline_ok=$true
}catch{
  $result.error=$_.Exception.Message
}finally{
  $result.completed_at=Get-Date
  $result|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $status -Encoding UTF8
}
if(-not $result.backfill_ok -or -not $result.baseline_ok){exit 1}
