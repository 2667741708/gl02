$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$catalog = Join-Path $root '数据库同步和存取\config\点位清单.tsv'
$stage = Join-Path $root 'logs\点位清单.static_pressure_af_20260716.staged.tsv'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$catalog.bak_static_pressure_af_$stamp"
$python = Join-Path $root '.venv\Scripts\python.exe'
$verifyScript = Join-Path $root 'logs\verify_22012_static_pressure_sync.20260716.py'
if (-not (Test-Path -LiteralPath $python)) { $python = 'C:\Program Files\Python311\python.exe' }

foreach ($path in @($catalog, $stage, $python, $verifyScript)) {
  if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}
$rows = Import-Csv -LiteralPath $stage -Delimiter "`t" -Encoding UTF8
$newRows = @($rows | Where-Object { $_.'变量名' -match '^P_static_(lower|middle|upper)_[A-F]$' })
if ($newRows.Count -ne 18) { throw "Staged catalog must contain exactly 18 A-F static-pressure rows; got $($newRows.Count)." }
if (@($newRows.'变量名' | Sort-Object -Unique).Count -ne 18) { throw 'Duplicate static-pressure variable_name.' }
if (@($newRows.'点ID/长名' | Sort-Object -Unique).Count -ne 18) { throw 'Duplicate static-pressure tag.' }

Copy-Item -LiteralPath $catalog -Destination $backup -Force
Copy-Item -LiteralPath $stage -Destination $catalog -Force

try {
  & $python -X utf8 -c "import sys; sys.path.insert(0, r'$root\数据库同步和存取\src'); from catalog import physical_points; p=physical_points(r'$root\数据库同步和存取\config\sync_config.json'); assert len(p)==133; assert len([x for x in p if x.variable_name.startswith('P_static_') and x.variable_name[-1:] in 'ABCDEF'])==18; print('catalog_physical_count=133 static_pressure_af=18')"
  if ($LASTEXITCODE -ne 0) { throw 'Remote catalog validation failed.' }

  & (Join-Path $root 'db_sync_storage\run_raw_5s_sync_pg_once.ps1') -Minutes 15 -BatchSize 133 -MaxWorkers 1
  if ($LASTEXITCODE -ne 0) { throw "Raw 5s sync smoke failed: $LASTEXITCODE" }

  & $python -X utf8 (Join-Path $root 'db_sync_storage\src\sync_from_243_pg.py') `
    --config (Join-Path $root 'db_sync_storage\config\sync_config.json') `
    --hours 0.25 --chunk-hours 0.25 --batch-size 133 --max-workers 1 --source-mode raw
  if ($LASTEXITCODE -ne 0) { throw "One-minute aggregate sync smoke failed: $LASTEXITCODE" }

  $verification = & $python -X utf8 $verifyScript
  Write-Output ($verification -join '')
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL verification query failed.' }
} catch {
  Copy-Item -LiteralPath $backup -Destination $catalog -Force
  throw
}

[pscustomobject]@{
  Stamp = $stamp
  CatalogBackup = $backup
  CatalogSha256 = (Get-FileHash -LiteralPath $catalog -Algorithm SHA256).Hash
  PhysicalPoints = 133
  StaticPressureAfPoints = 18
  PostgreSql = ($verification -join '')
  ContinuousTask = (Get-ScheduledTask -TaskName 'BlastFurnaceV3PgContinuousSync30s').State.ToString()
} | ConvertTo-Json -Depth 4
