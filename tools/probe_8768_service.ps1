$ErrorActionPreference = "Stop"
$svc = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewWs8768'"
$listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
[ordered]@{
    serviceState = $svc.State
    servicePath = $svc.PathName
    listenerPid = if ($listener) { $listener.OwningProcess } else { $null }
    pythonProcesses = @(Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*Python311*' } | Select-Object Id,Path,StartTime)
} | ConvertTo-Json -Depth 4
