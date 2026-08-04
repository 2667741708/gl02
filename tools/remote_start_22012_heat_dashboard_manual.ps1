$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$runner = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\run_22012_heat_dashboard_8891.ps1"
$powershell = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
[ordered]@{
    runner = $runner
    runner_exists = Test-Path -LiteralPath $runner
    powershell_exists = Test-Path -LiteralPath $powershell
} | ConvertTo-Json -Depth 4
$proc = Start-Process -FilePath $powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 8
[ordered]@{
    process_id = $proc.Id
    process_exists = [bool](Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)
    listener = @(Get-NetTCPConnection -State Listen -LocalPort 8891 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess)
    log = if (Test-Path -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\logs\heat_dashboard_8891.log") { Get-Content -LiteralPath "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\logs\heat_dashboard_8891.log" -Tail 50 } else { @() }
} | ConvertTo-Json -Depth 8
