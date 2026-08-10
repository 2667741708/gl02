param(
    [string]$ProjectRoot = '',
    [string]$TaskName = 'IMESBF2OperationLogReport5m'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = if ($ProjectRoot) { $ProjectRoot } else { (Get-Location).Path }
$scriptPath = Get-ChildItem -LiteralPath $ProjectRoot -Filter 'run_22012_bf2_operation_log_report_sync.ps1' -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $scriptPath) {
    throw "report sync entrypoint not found under $ProjectRoot"
}

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$start = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
