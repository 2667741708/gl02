$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$taskNames = @(
    "BFOllama11434HealthCheck",
    "BlastFurnaceV3Proxy8092",
    "BlastFurnaceV3Proxy8093",
    "BlastFurnace8093Proxy_NewProject",
    "BaselineProxy8092",
    "V4PreviewProxy8093",
    "V3AutoPreviewProxy8094"
)

$taskRows = @()
foreach ($taskName in $taskNames) {
    $tasks = @(Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)
    foreach ($task in $tasks) {
        $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
        $taskRows += [pscustomobject]@{
            task_path = $task.TaskPath
            task_name = $task.TaskName
            state = [string]$task.State
            enabled = [bool]$task.Settings.Enabled
            last_run_time = if ($info) { $info.LastRunTime } else { $null }
            last_task_result = if ($info) { $info.LastTaskResult } else { $null }
            actions = @($task.Actions | ForEach-Object {
                [pscustomobject]@{
                    execute = [string]$_.Execute
                    arguments = [string]$_.Arguments
                    working_directory = [string]$_.WorkingDirectory
                }
            })
            triggers = @($task.Triggers | ForEach-Object {
                [pscustomobject]@{
                    cim_class = $_.CimClass.CimClassName
                    enabled = [bool]$_.Enabled
                    start_boundary = [string]$_.StartBoundary
                    end_boundary = [string]$_.EndBoundary
                    repetition_interval = [string]$_.Repetition.Interval
                    repetition_duration = [string]$_.Repetition.Duration
                    repetition_stop_at_duration_end = [bool]$_.Repetition.StopAtDurationEnd
                    delay = [string]$_.Delay
                    user_id = [string]$_.UserId
                }
            })
        }
    }
}

$candidatePaths = @()
foreach ($task in $taskRows) {
    foreach ($action in @($task.actions)) {
        $match = [regex]::Match($action.arguments, '(?i)-File\s+(?:"([^"]+)"|([^\s]+))')
        if ($match.Success) {
            $candidatePaths += if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
        }
    }
}
$candidatePaths += @(
    "F:\高炉炼铁项目-real-sensor-v2_V3\tools\run_proxy_8092_forever.ps1",
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_v4_8093_proxy_forever.ps1",
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8094_preview.ps1"
)

$fileRows = @()
foreach ($path in @($candidatePaths | Sort-Object -Unique)) {
    $exists = Test-Path -LiteralPath $path
    $matches = @()
    if ($exists) {
        $matches = @(Select-String -LiteralPath $path -Pattern @(
            "BF_LLM_MODEL",
            "DEFAULT_MODEL",
            "--model",
            "chiqiong-blast-furnace",
            "bf-diagnosis-runtime",
            "OLLAMA_BASE_URL",
            "OLLAMA_HOST",
            "api/chat",
            "api/generate"
        ) -SimpleMatch -ErrorAction SilentlyContinue | ForEach-Object {
            [pscustomobject]@{
                line_number = $_.LineNumber
                line = $_.Line.Trim()
            }
        })
    }
    $fileRows += [pscustomobject]@{
        path = $path
        exists = $exists
        matches = $matches
    }
}

$searchRoots = @(
    "F:\高炉炼铁项目-real-sensor-v2_V3\高炉前端数据",
    "F:\高炉炼铁项目-real-sensor-v2_8093\高炉前端数据",
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据"
)
$searchRows = @()
foreach ($root in $searchRoots) {
    if (-not (Test-Path -LiteralPath $root)) {
        continue
    }
    $files = @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Length -le 2MB -and
            $_.Extension -in @(".ps1", ".cmd", ".bat", ".py", ".json", ".yaml", ".yml")
        })
    foreach ($file in $files) {
        $matches = @(Select-String -LiteralPath $file.FullName -Pattern @(
            "chiqiong-blast-furnace:latest",
            "chiqiong-blast-furnace:latest_M",
            "bf-diagnosis-runtime:v1"
        ) -SimpleMatch -ErrorAction SilentlyContinue)
        if ($matches.Count -eq 0) {
            continue
        }
        $searchRows += [pscustomobject]@{
            path = $file.FullName
            matches = @($matches | Select-Object -First 60 | ForEach-Object {
                [pscustomobject]@{
                    line_number = $_.LineNumber
                    line = $_.Line.Trim()
                }
            })
        }
    }
}

[pscustomobject]@{
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    tasks = $taskRows
    candidate_files = $fileRows
    model_references = $searchRows
} | ConvertTo-Json -Depth 15
