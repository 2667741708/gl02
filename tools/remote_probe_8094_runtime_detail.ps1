$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'V3AutoPreviewProxy8094'
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$ports = foreach ($port in @(8093, 8094, 8768, 8770, 11434)) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    [ordered]@{
        port = $port
        pid = if ($listener) { [int]$listener.OwningProcess } else { $null }
    }
}
$processes = Get-CimInstance Win32_Process -ErrorAction Stop |
    Where-Object {
        $_.CommandLine -and
        ($_.CommandLine.Contains($root) -or $_.CommandLine.Contains('remote_guarded_enable_8094_core19_r7.ps1')) -and
        ($_.Name -in @('python.exe', 'powershell.exe', 'pwsh.exe'))
    } |
    Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine
$logPath = Join-Path $root 'logs\preview_proxy_8094.log'
$logTail = if (Test-Path -LiteralPath $logPath) {
    @(Get-Content -LiteralPath $logPath -Tail 40 -ErrorAction SilentlyContinue)
}
else {
    @()
}

[ordered]@{
    checkedAt = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    task = [ordered]@{
        state = [string]$task.State
        lastRunTime = $taskInfo.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss')
        lastTaskResult = [int]$taskInfo.LastTaskResult
    }
    ports = $ports
    processes = @($processes)
    logTail = $logTail
} | ConvertTo-Json -Depth 6
