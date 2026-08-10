$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = 'python'
$remote = Join-Path $root 'tools\remote_22012_exec.py'
$workdir = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$syncDir = "$workdir\数据库同步和存取\src"
$configPath = "$workdir\数据库同步和存取\config\sync_config.json"

# All 18 foreman variables that need 30-day data
$vars = "Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel,BlastEnergy,BlastSpeedStd,BlastSpeedActual,Q_N2,P_N2,P_O2_valve_in,P_O2_valve_out,Hopper_weight,CO_top,CO2_top,H2_top,PCI_previous_hour"

Write-Host "=== STEP 1: pSpace 30-day backfill ==="
$cmd1 = "`$env:PSPACE_USER=$env:PSPACE_USER; `$env:PSPACE_PASSWORD=$env:PSPACE_PASSWORD; cd '$workdir'; & 'C:\Program Files\Python311\python.exe' .\数据库同步和存取\src\sync_from_243_pg.py --config .\数据库同步和存取\config\sync_config.json --days 30 --chunk-hours 12 --batch-size 6 --max-workers 1 --source-mode processed --source-aggregate average --target-aggregate PS_HIS_AVERAGE --target-interval-seconds 60 --no-persist-raw-5s --variables $vars --skip-retention 2>&1"
& $python $remote --allow-agents-password --no-profile --timeout 600 --workdir $workdir --command $cmd1
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: Step 1 failed (exit=$LASTEXITCODE) - continuing to step 2 anyway" }

Write-Host "=== STEP 2: Upload latest baseline_maintainer.py ==="
$uploads = @(
    "$(Join-Path $root '自动诊断服务\baseline_maintainer.py')=$workdir\自动诊断服务\baseline_maintainer.py",
    "$(Join-Path $root '自动诊断服务\store.py')=$workdir\自动诊断服务\store.py",
    "$(Join-Path $root '自动诊断服务\service_config.py')=$workdir\自动诊断服务\service_config.py",
    "$(Join-Path $root '自动诊断服务\schema.sql')=$workdir\自动诊断服务\schema.sql",
    "$(Join-Path $root '自动诊断服务\abc_rule_schema.sql')=$workdir\自动诊断服务\abc_rule_schema.sql"
)
& $python $remote --allow-agents-password --no-profile --timeout 40 --workdir $workdir --upload-only @($uploads | ForEach-Object { '--upload'; $_ })
if ($LASTEXITCODE -ne 0) { throw "upload failed" }

Write-Host "=== STEP 3: 30-day baseline backfill (derived first, then cooling) ==="
$cmd3 = "cd '$workdir'; & 'C:\Program Files\Python311\python.exe' .\自动诊断服务\baseline_maintainer.py --backfill-days 30 --derived-only --write 2>&1; Write-Host '---DERIVED DONE---'; & 'C:\Program Files\Python311\python.exe' .\自动诊断服务\baseline_maintainer.py --backfill-days 30 --cooling-only --write 2>&1; Write-Host '---COOLING DONE---'"
& $python $remote --allow-agents-password --no-profile --timeout 300 --workdir $workdir --command $cmd3
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: Step 3 failed" }

Write-Host "=== RECOVERY COMPLETE ==="
