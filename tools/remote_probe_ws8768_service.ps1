$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$service = Get-CimInstance -ClassName Win32_Service -Filter "Name='BFV4PreviewWs8768'"
$listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$process = $null
if ($service.ProcessId -gt 0) {
    $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$($service.ProcessId)" -ErrorAction SilentlyContinue
}

[ordered]@{
    name = $service.Name
    state = $service.State
    processId = [int]$service.ProcessId
    pathName = $service.PathName
    serviceProcess = if ($process) { $process.CommandLine } else { $null }
    listenerPid = if ($listener) { [int]$listener.OwningProcess } else { $null }
} | ConvertTo-Json -Depth 4
