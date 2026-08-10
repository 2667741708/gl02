$ErrorActionPreference = 'Stop'

$service = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewWs8768'"
if (-not $service) {
    throw 'BFV4PreviewWs8768 service was not found'
}

[pscustomobject]@{
    kind = 'service'
    name = $service.Name
    state = $service.State
    process_id = $service.ProcessId
    path_name = $service.PathName
} | ConvertTo-Json -Compress

Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -like '*local_pg_ws_bridge.py*' } |
    ForEach-Object {
        [pscustomobject]@{
            kind = 'process'
            process_id = $_.ProcessId
            parent_process_id = $_.ParentProcessId
            executable_path = $_.ExecutablePath
            command_line = $_.CommandLine
        } | ConvertTo-Json -Compress
    }
