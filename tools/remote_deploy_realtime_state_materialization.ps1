$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)

$root='F:\高炉炼铁项目-real-sensor-v2_V3\数据库同步和存取'
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_state_materialization'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$backup=Join-Path $root ("backups\state_materialization_$stamp")
$python='C:\Program Files\Python311\python.exe'

if(-not(Test-Path -LiteralPath $python)){throw 'Python311 is unavailable'}
if(-not(Test-Path -LiteralPath $stage)){throw 'staging directory is unavailable'}
New-Item -ItemType Directory -Path $backup -Force | Out-Null

$files=@(
  @{Source=(Join-Path $stage 'sync_from_243_pg.py');Target=(Join-Path $root 'src\sync_from_243_pg.py')},
  @{Source=(Join-Path $stage 'raw_minute_pipeline.py');Target=(Join-Path $root 'src\raw_minute_pipeline.py')},
  @{Source=(Join-Path $stage 'pg_store.py');Target=(Join-Path $root 'src\pg_store.py')},
  @{Source=(Join-Path $stage 'sync_config.json');Target=(Join-Path $root 'config\sync_config.json')}
)

foreach($item in $files){
  if(-not(Test-Path -LiteralPath $item.Source)){throw "missing staged file: $($item.Source)"}
  if(-not(Test-Path -LiteralPath $item.Target)){throw "missing target file: $($item.Target)"}
}

& $python -m py_compile (Join-Path $stage 'sync_from_243_pg.py')
if($LASTEXITCODE-ne0){throw 'sync_from_243_pg.py syntax validation failed'}
& $python -m py_compile (Join-Path $stage 'raw_minute_pipeline.py')
if($LASTEXITCODE-ne0){throw 'raw_minute_pipeline.py syntax validation failed'}
& $python -m py_compile (Join-Path $stage 'pg_store.py')
if($LASTEXITCODE-ne0){throw 'pg_store.py syntax validation failed'}
Get-Content -LiteralPath (Join-Path $stage 'sync_config.json') -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null

foreach($item in $files){
  Copy-Item -LiteralPath $item.Target -Destination (Join-Path $backup (Split-Path $item.Target -Leaf)) -Force
}

foreach($item in $files){
  $next="$($item.Target).next"
  Copy-Item -LiteralPath $item.Source -Destination $next -Force
  Move-Item -LiteralPath $next -Destination $item.Target -Force
}

$wrapper=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like '*run_realtime_sync_pg_bg.ps1*'}
if(-not$wrapper){throw 'realtime sync wrapper is not running'}

$result=@{
  ok=$true
  backup=$backup
  wrapper_pid=@($wrapper.ProcessId)
  deployed=@()
}
foreach($item in $files){
  $result.deployed+=@{
    path=$item.Target
    sha256=(Get-FileHash -LiteralPath $item.Target -Algorithm SHA256).Hash
  }
}
$result | ConvertTo-Json -Depth 5
