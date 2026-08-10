$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$syncRoot = "F:\高炉炼铁项目-real-sensor-v2_V3\db_sync_storage"
$target = Join-Path $syncRoot "src\sync_from_243_pg.py"
$stage = "C:\Users\Administrator\AppData\Local\Temp\abc_final_sync_from_243_pg.py"
$backup = "$target.isolated_probe_backup"
$variables = "Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel"
Copy-Item -LiteralPath $target -Destination $backup -Force
Copy-Item -LiteralPath $stage -Destination $target -Force
Push-Location $syncRoot
try {
    & python ".\src\sync_from_243_pg.py" --start-time "2026-05-13 05:36:00" --end-time "2026-05-13 06:36:00" --chunk-hours 1 --batch-size 6 --max-workers 1 --source-mode processed --source-aggregate average --target-aggregate PS_HIS_AVERAGE --target-interval-seconds 60 --no-persist-raw-5s --variables $variables --skip-retention
    if ($LASTEXITCODE -ne 0) { throw "isolated pSpace chunk failed" }
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    throw
} finally { Pop-Location }
Write-Output "isolated_chunk_ok=true"
