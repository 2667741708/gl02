$ErrorActionPreference = "Stop"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8095"
$runner = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8095_preview.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Start-Sleep -Seconds 4
Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Select-Object TaskName,State
Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
