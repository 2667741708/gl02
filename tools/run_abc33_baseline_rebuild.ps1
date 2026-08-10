param(
  [int]$BackfillDays=1,
  [string]$EndDay=''
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$python='C:\Program Files\Python311\python.exe'
$script=Get-ChildItem -LiteralPath $root -Directory|ForEach-Object{
  $candidate=Join-Path $_.FullName 'baseline_maintainer.py'
  if(Test-Path -LiteralPath $candidate){Get-Item -LiteralPath $candidate}
}|Select-Object -First 1
if(-not$script){throw 'V4 baseline maintainer not found'}
$config=Join-Path $script.DirectoryName 'config.yaml'
$verify=Join-Path $PSScriptRoot 'verify_abc33_baseline_coverage.py'
if(-not(Test-Path -LiteralPath $config)){throw 'V4 baseline config not found'}
if(-not(Test-Path -LiteralPath $verify)){throw 'ABC33 baseline verifier not found'}
$effectiveEnd=if($EndDay){$EndDay}else{(Get-Date).Date.ToString('yyyy-MM-dd')}
$log=Join-Path $root ('logs\abc33_baseline_rebuild_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.json')
&$python -X utf8 $script.FullName --backfill-days $BackfillDays --end-day $effectiveEnd --baseline-days 30 --write --config $config|Out-File -LiteralPath $log -Encoding UTF8
if($LASTEXITCODE-ne0){throw 'ABC33 historical baseline rebuild failed'}
&$python -X utf8 $verify --day $effectiveEnd --minimum-coverage 0.75
if($LASTEXITCODE-ne0){throw 'ABC33 baseline quality gate failed'}
[pscustomobject]@{ok=$true;end_day=$effectiveEnd;backfill_days=$BackfillDays;calculation_log=$log}|ConvertTo-Json
