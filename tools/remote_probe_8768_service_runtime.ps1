$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$service = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewWs8768'"
if (-not $service) {
    throw 'BFV4PreviewWs8768 service not found'
}

$processInfo = $null
if ($service.ProcessId -gt 0) {
    $processInfo = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $service.ProcessId)
}

$nssm = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\nssm\nssm-2.24\win64\nssm.exe'
$nssmConfig = [ordered]@{}
foreach ($key in @('Application', 'AppDirectory', 'AppParameters', 'AppEnvironmentExtra', 'AppStdout', 'AppStderr')) {
    $value = & $nssm get 'BFV4PreviewWs8768' $key 2>$null
    $nssmConfig[$key] = ($value -join "`n")
}

[ordered]@{
    service = [ordered]@{
        name = $service.Name
        state = $service.State
        start_mode = $service.StartMode
        start_name = $service.StartName
        process_id = $service.ProcessId
        path_name = $service.PathName
    }
    process = if ($processInfo) {
        [ordered]@{
            executable = $processInfo.ExecutablePath
            command_line = $processInfo.CommandLine
            parent_process_id = $processInfo.ParentProcessId
        }
    } else {
        $null
    }
    nssm = $nssmConfig
} | ConvertTo-Json -Depth 5
