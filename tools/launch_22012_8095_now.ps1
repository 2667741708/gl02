$ErrorActionPreference = "Stop"
$runner = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8095_preview.ps1"
Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner)
Start-Sleep -Seconds 6
Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
