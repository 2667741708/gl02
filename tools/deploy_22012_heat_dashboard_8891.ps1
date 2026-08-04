$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
$taskPath = "\BlastFurnaceServices\"
$taskName = "StandaloneHeatDashboard8891"
$runner = "$root\run_22012_heat_dashboard_8891.ps1"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$secretFiles = @(
    "$root\PT\imes_vastbase.local.env",
    "$root\PT\external_sources.local.env"
)
$backupRoot = "$root\backups"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

$required = @(
    "$root\db_dashboard\server.py",
    "$root\db_dashboard\heat_service.py",
    "$root\db_dashboard\external_sources.py",
    "$root\db_dashboard\heat_data_explorer.js",
    "$root\db_dashboard\heat.html",
    "$root\db_dashboard\index.html",
    "$root\自动诊断服务\recommendation_adapter.py",
    "$root\调控结论生成引擎\recommendation\__init__.py",
    "$root\高炉前端数据\libs\echarts.min.js",
    $runner
)
$required += $secretFiles
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "missing deployment file: $path"
    }
}

New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$backup = Join-Path $backupRoot ("heat_dashboard_8891_" + $timestamp)
New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($relative in @("db_dashboard", "高炉前端数据\libs", "自动诊断服务", "调控结论生成引擎\recommendation", "PT", "run_22012_heat_dashboard_8891.ps1")) {
    $source = Join-Path $root $relative
    if (Test-Path -LiteralPath $source) {
        $destination = Join-Path $backup $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }
}

# Keep credential files outside the web root and readable only by local administrators/SYSTEM.
foreach ($secretFile in $secretFiles) {
    & icacls.exe $secretFile /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
}

try {
    $oldTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    if ($oldTask) {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
} catch { }

$managed = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$root*db_dashboard*server.py*" }
foreach ($process in $managed) {
    Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction SilentlyContinue
}

$ruleName = "BlastFurnaceStandaloneHeatDashboard8891"
if (-not (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $ruleName -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8891 -Profile Domain,Private | Out-Null
}

$action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName

$deadline = (Get-Date).AddSeconds(5)
$listener = $null
while ((Get-Date) -lt $deadline) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 8891 -ErrorAction SilentlyContinue | Select-Object -First 1 LocalAddress,LocalPort,OwningProcess
    if ($listener) { break }
    Start-Sleep -Seconds 1
}

$rootStatus = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8891/" -TimeoutSec 4
$overviewStatus = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8891/api/overview" -TimeoutSec 4
$heatsStatus = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8891/api/heats?limit=1&furnace=2" -TimeoutSec 4

[ordered]@{
    task = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Select-Object TaskName,State,TaskPath)
    listener = $listener
    root_http_status = $rootStatus.StatusCode
    overview_http_status = $overviewStatus.StatusCode
    heats_http_status = $heatsStatus.StatusCode
    backup = $backup
    firewall_rule = $ruleName
} | ConvertTo-Json -Depth 8
