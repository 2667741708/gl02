# Sync cooling variables from pSpace one day at a time
$ErrorActionPreference = 'Continue'
$python = 'C:\Program Files\Python311\python.exe'
$syncScript = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\数据库同步和存取\src\sync_from_243_pg.py'
$config = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\数据库同步和存取\config\sync_config.json'
$vars = 'Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel'
$startDate = Get-Date '2026-05-25'
$endDate = Get-Date '2026-08-09'
$current = $startDate
$ok = 0
$bad = 0

while ($current -le $endDate) {
    $dayStr = $current.ToString('yyyy-MM-dd')
    $nextDay = $current.AddDays(1).ToString('yyyy-MM-dd')
    $startArg = "$dayStr 00:00:00"
    $endArg = "$nextDay 00:00:00"
    Write-Host "[$dayStr] ..."
    $process = Start-Process -FilePath $python -ArgumentList "-X", "utf8", $syncScript, "--config", $config, "--start-time", $startArg, "--end-time", $endArg, "--chunk-hours", "4", "--batch-size", "3", "--max-workers", "1", "--source-mode", "raw", "--source-interval-seconds", "5", "--source-aggregate", "average", "--target-aggregate", "PS_RAW_AVERAGE", "--target-interval-seconds", "60", "--no-persist-raw-5s", "--variables", $vars, "--skip-retention" -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -eq 0) {
        $ok++
        Write-Host "  OK (ok=$ok bad=$bad)"
    } else {
        $bad++
        Write-Host "  FAIL (rc=$($process.ExitCode))"
        if ($bad -ge 5) { Write-Host "Too many failures"; break }
    }
    $current = $current.AddDays(1)
}
Write-Host "DONE: $ok ok, $bad bad"
