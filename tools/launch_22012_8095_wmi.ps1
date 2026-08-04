$ErrorActionPreference = "Stop"
$runner = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8095_preview.ps1"
$commandLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $commandLine }
[ordered]@{ ReturnValue = $result.ReturnValue; ProcessId = $result.ProcessId; CommandLine = $commandLine } | ConvertTo-Json
Start-Sleep -Seconds 8
Get-NetTCPConnection -LocalPort 8095 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
