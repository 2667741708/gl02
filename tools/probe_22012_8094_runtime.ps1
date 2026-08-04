$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$connection = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)"
$parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
$task = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -InputObject $task
$matching = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains("F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server.py")
} | ForEach-Object {
    $candidateParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.ParentProcessId)" -ErrorAction SilentlyContinue
    [ordered]@{
        ProcessId = $_.ProcessId
        CreationDate = $_.CreationDate.ToString("yyyy-MM-dd HH:mm:ss")
        ParentProcessId = $_.ParentProcessId
        ParentExists = [bool]$candidateParent
        ParentCommandLine = if ($candidateParent) { $candidateParent.CommandLine } else { $null }
        Listening8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1)
        Listening8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
})
[ordered]@{
    Port = [ordered]@{
        LocalAddress = $connection.LocalAddress
        OwningProcess = $connection.OwningProcess
    }
    Process = [ordered]@{
        Name = $process.Name
        CreationDate = $process.CreationDate.ToString("yyyy-MM-dd HH:mm:ss")
        CommandLine = $process.CommandLine
        ParentProcessId = $process.ParentProcessId
    }
    ParentProcess = if ($parent) {
        [ordered]@{
            Name = $parent.Name
            CreationDate = $parent.CreationDate.ToString("yyyy-MM-dd HH:mm:ss")
            CommandLine = $parent.CommandLine
            ParentProcessId = $parent.ParentProcessId
        }
    } else { $null }
    Task = [ordered]@{
        State = $task.State.ToString()
        LastRunTime = $taskInfo.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")
        LastTaskResult = $taskInfo.LastTaskResult
    }
    MatchingPreviewProcesses = $matching
} | ConvertTo-Json -Depth 8
