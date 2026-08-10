$ErrorActionPreference = 'Stop'
$listener = Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction Stop | Select-Object -First 1
$listenerPid = [int]$listener.OwningProcess
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid"
$parent = if ($process) { Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" }
$protected = [ordered]@{}
foreach ($port in @(8093, 8094, 8768, 8770)) {
    $entry = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    $protected[[string]$port] = if ($entry) { [int]$entry.OwningProcess } else { $null }
}
[ordered]@{
    listener_pid = $listenerPid
    protected_listeners = $protected
    services = [ordered]@{
        BFV4PreviewProxy8093 = [string](Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction SilentlyContinue).Status
        BFV4PreviewWs8768 = [string](Get-Service -Name 'BFV4PreviewWs8768' -ErrorAction SilentlyContinue).Status
    }
    process_name = $process.Name
    process_id = $process.ProcessId
    parent_pid = $process.ParentProcessId
    process_command = $process.CommandLine
    parent_command = $parent.CommandLine
    task_state = [string](Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V4BillboardPspace8770' -ErrorAction SilentlyContinue).State
    task_actions = @((Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V4BillboardPspace8770' -ErrorAction SilentlyContinue).Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments })
} | ConvertTo-Json -Depth 4
