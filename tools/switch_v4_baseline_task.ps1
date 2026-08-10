$ErrorActionPreference = 'Stop'
$taskName = 'BlastFurnace8093DailyBaseline20d'
$taskPath = '\'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$wrapper = Join-Path $root 'tools\run_v4_daily_baseline.ps1'
$maintainer = Join-Path $root '自动诊断服务\baseline_maintainer.py'
if (-not (Test-Path -LiteralPath $wrapper)) { throw "V4 wrapper missing: $wrapper" }
if (-not (Test-Path -LiteralPath $maintainer)) { throw "V4 baseline maintainer missing: $maintainer" }
$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $root ("backups\baseline_task_switch_{0}" -f $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Export-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Set-Content -LiteralPath (Join-Path $backupDir 'task_before.xml') -Encoding UTF8
$task.Actions | Select-Object Execute,Arguments,WorkingDirectory | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backupDir 'action_before.json') -Encoding UTF8
$argument = '-NoProfile -ExecutionPolicy Bypass -File "' + $wrapper + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
Set-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Action $action | Out-Null
$after = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath
$afterAction = $after.Actions | Select-Object Execute,Arguments,WorkingDirectory
if ($afterAction.Execute -ne 'powershell.exe' -or $afterAction.Arguments -ne $argument) {
    throw 'Scheduled task action verification failed'
}
[pscustomobject]@{
    ok = $true
    task = $taskName
    task_state = [string]$after.State
    execute = $afterAction.Execute
    arguments = $afterAction.Arguments
    backup_dir = $backupDir
    maintainer = $maintainer
} | ConvertTo-Json -Depth 4
