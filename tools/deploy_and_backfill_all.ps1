# One-click: deploy baseline scripts + run today's baseline + backfill pSpace history
# Run on 220.12 as Administrator
$ErrorActionPreference = 'Continue'
$py = 'C:\Program Files\Python311\python.exe'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$vars = 'Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel'

Write-Host "=== STEP 1: Deploy updated files ==="
Copy-Item -Force "$root\tools\run_v4_daily_baseline.ps1" "$root\tools\run_v4_daily_baseline.ps1.bak" -ErrorAction SilentlyContinue
Write-Host "  (baseline_maintainer.py already uploaded via paramiko)"
Write-Host "  (run_v4_daily_baseline.ps1 already uploaded via paramiko)"

Write-Host "=== STEP 2: Today's baselines (cooling + foreman) ==="
foreach ($mode in @('--cooling-only','--foreman-only')) {
    Write-Host "  Running $mode ..."
    & $py -X utf8 "$root\自动诊断服务\baseline_maintainer.py" --build-day 2026-08-09 --baseline-days 30 $mode --write
    if ($LASTEXITCODE -eq 0) { Write-Host "    OK" } else { Write-Host "    FAIL (rc=$LASTEXITCODE)" }
}

Write-Host "=== STEP 3: pSpace backfill (Jul 10 - Aug 6, one day at a time) ==="
$start = Get-Date '2026-07-10'
$end = Get-Date '2026-08-06'
$ok = 0; $bad = 0
while ($start -le $end) {
    $d = $start.ToString('yyyy-MM-dd')
    $n = $start.AddDays(1).ToString('yyyy-MM-dd')
    Write-Host -NoNewline "  [$d] ... "
    $p = Start-Process -FilePath $py -ArgumentList @(
        '-X','utf8',
        "$root\数据库同步和存取\src\sync_from_243_pg.py",
        '--config',"$root\数据库同步和存取\config\sync_config.json",
        '--start-time',"$d 00:00:00",
        '--end-time',"$n 00:00:00",
        '--chunk-hours','6',
        '--batch-size','3',
        '--max-workers','1',
        '--source-mode','processed',
        '--source-aggregate','average',
        '--target-aggregate','PS_HIS_AVERAGE',
        '--target-interval-seconds','60',
        '--no-persist-raw-5s',
        '--variables',$vars,
        '--skip-retention'
    ) -NoNewWindow -Wait -PassThru
    if ($p.ExitCode -eq 0) { $ok++; Write-Host "OK ($ok ok, $bad bad)" }
    else { $bad++; Write-Host "FAIL rc=$($p.ExitCode) ($ok ok, $bad bad)"; if ($bad -ge 5) { Write-Host "Too many failures"; break } }
    $start = $start.AddDays(1)
}

Write-Host "=== STEP 4: Rebuild 30-day baseline for all new data ==="
& $py -X utf8 "$root\自动诊断服务\baseline_maintainer.py" --backfill-days 30 --cooling-only --write
Write-Host "  cooling: rc=$LASTEXITCODE"
& $py -X utf8 "$root\自动诊断服务\baseline_maintainer.py" --backfill-days 30 --foreman-only --write
Write-Host "  foreman: rc=$LASTEXITCODE"
& $py -X utf8 "$root\自动诊断服务\baseline_maintainer.py" --backfill-days 30 --derived-only --write
Write-Host "  derived: rc=$LASTEXITCODE"

Write-Host "=== ALL DONE: $ok pSpace days ok, $bad failed ==="
