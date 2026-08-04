$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$targets = [ordered]@{
    "8093" = Join-Path $frontend "frontend_dashboard_v3.server.html"
    "8094" = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
}

$files = [ordered]@{}
foreach ($entry in $targets.GetEnumerator()) {
    $exists = Test-Path -LiteralPath $entry.Value
    $text = if ($exists) { Get-Content -Raw -LiteralPath $entry.Value -Encoding UTF8 } else { "" }
    $files[$entry.Key] = [ordered]@{
        Path = $entry.Value
        Exists = $exists
        Length = if ($exists) { (Get-Item -LiteralPath $entry.Value).Length } else { 0 }
        LastWriteTime = if ($exists) { (Get-Item -LiteralPath $entry.Value).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss") } else { $null }
        SHA256 = if ($exists) { (Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256).Hash } else { $null }
        HasAdaptiveFix = $text.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
        HasFormalHeader = $text.Contains("topbar branded-topbar")
    }
}

$services = Get-Service -Name "BFV4PreviewProxy8093", "BFV4PreviewWs8768" -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType
$task = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction SilentlyContinue
$taskInfo = if ($task) { Get-ScheduledTaskInfo -InputObject $task } else { $null }

$http = [ordered]@{}
foreach ($port in 8093, 8094) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/?t=probe-responsive-20260716#overview" -TimeoutSec 45
        $http["$port"] = [ordered]@{
            Status = [int]$response.StatusCode
            Length = $response.Content.Length
            HasAdaptiveFix = $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
            HasFormalHeader = $response.Content.Contains("topbar branded-topbar")
        }
    }
    catch {
        $http["$port"] = [ordered]@{ Error = $_.Exception.Message }
    }
}

[ordered]@{
    ComputerName = $env:COMPUTERNAME
    Files = $files
    Services = @($services)
    Ports = [ordered]@{
        "8093" = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        "8094" = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        "8768" = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
    Preview8094Task = if ($task) {
        [ordered]@{
            State = $task.State.ToString()
            LastRunTime = $taskInfo.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss")
            LastTaskResult = $taskInfo.LastTaskResult
            Execute = $task.Actions.Execute
            Arguments = $task.Actions.Arguments
        }
    } else { $null }
    Http = $http
} | ConvertTo-Json -Depth 8
