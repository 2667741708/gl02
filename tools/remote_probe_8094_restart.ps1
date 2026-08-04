$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
$listener = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$processes = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine.Contains("run_22012_8094_preview.ps1") -or
                (
                    $_.CommandLine.Contains("ollama_proxy_server.py") -and
                    $_.CommandLine.Contains("V4_8093_PREVIEW")
                )
            )
        } |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine
)
$log = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\preview_proxy_8094.log"
[ordered]@{
    checkedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    taskState = if ($task) { $task.State.ToString() } else { "Missing" }
    lastRunTime = $info.LastRunTime
    lastTaskResult = $info.LastTaskResult
    listenerPid = $listener.OwningProcess
    processes = $processes
    logTail = if (Test-Path -LiteralPath $log) {
        @(Get-Content -LiteralPath $log -Tail 20 -Encoding UTF8)
    } else {
        @("log missing")
    }
} | ConvertTo-Json -Depth 5
