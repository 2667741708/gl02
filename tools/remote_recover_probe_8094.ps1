$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$logPath = Join-Path $root "logs\preview_proxy_8094.log"
$runnerPath = Join-Path $root "tools\run_22012_8094_preview.ps1"
$restartPath = Join-Path $root "tools\restart_22012_8094_preview.ps1"

$listenerMap = @{}
$netstatLines = @(& "$env:SystemRoot\System32\netstat.exe" -ano -p tcp)
foreach ($line in $netstatLines) {
    if ($line -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$') {
        $port = [int]$Matches[1]
        if (-not $listenerMap.ContainsKey($port)) {
            $listenerMap[$port] = [int]$Matches[2]
        }
    }
}

function Get-ListenerPid {
    param([Parameter(Mandatory = $true)][int]$Port)
    if (-not $listenerMap.ContainsKey($Port)) { return $null }
    return [int]$listenerMap[$Port]
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$tail = @()
if (Test-Path -LiteralPath $logPath -PathType Leaf) {
    $tail = @(Get-Content -LiteralPath $logPath -Tail 40 -Encoding UTF8)
}

[ordered]@{
    taskState = [string]$task.State
    lastRunTime = $taskInfo.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")
    lastTaskResult = [int64]$taskInfo.LastTaskResult
    pid8093 = Get-ListenerPid -Port 8093
    pid8094 = Get-ListenerPid -Port 8094
    pid8768 = Get-ListenerPid -Port 8768
    pid8769 = Get-ListenerPid -Port 8769
    pid8770 = Get-ListenerPid -Port 8770
    pid11434 = Get-ListenerPid -Port 11434
    runnerExists = Test-Path -LiteralPath $runnerPath -PathType Leaf
    runnerSha256 = if (Test-Path -LiteralPath $runnerPath -PathType Leaf) { (Get-FileHash -LiteralPath $runnerPath -Algorithm SHA256).Hash } else { $null }
    restartExists = Test-Path -LiteralPath $restartPath -PathType Leaf
    logTail = $tail
} | ConvertTo-Json -Depth 6
