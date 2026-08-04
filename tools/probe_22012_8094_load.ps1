$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$listener = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
$process = Get-Process -Id $listener.OwningProcess -ErrorAction Stop
$connections = @(Get-NetTCPConnection -LocalPort 8094 -ErrorAction SilentlyContinue)
$states = @($connections | Group-Object State | ForEach-Object {
    [ordered]@{ State = $_.Name; Count = $_.Count }
})

[ordered]@{
    ProcessId = $process.Id
    StartTime = $process.StartTime.ToString("yyyy-MM-dd HH:mm:ss")
    CPU = $process.CPU
    Threads = $process.Threads.Count
    Handles = $process.HandleCount
    WorkingSetMB = [Math]::Round($process.WorkingSet64 / 1MB, 1)
    PrivateMemoryMB = [Math]::Round($process.PrivateMemorySize64 / 1MB, 1)
    TcpStates = $states
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
} | ConvertTo-Json -Depth 6
