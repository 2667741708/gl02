$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$IncludeScriptContent = $false

$projectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$taskPath = "\BlastFurnaceServices\"
$taskName = "BFV4PreviewProxy8093HealthCheck"
$healthScriptPath = Join-Path $projectRoot "tools\check_managed_nssm_service_health.ps1"
$configPath = Join-Path $projectRoot "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$healthLogPath = Join-Path $projectRoot "logs\proxy_8093.health.log"
$statePath = Join-Path $projectRoot "logs\proxy_8093.health.state.json"

$task = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath -ErrorAction Stop
$actions = @($task.Actions | ForEach-Object {
    [pscustomobject]@{
        execute = [string]$_.Execute
        arguments = [string]$_.Arguments
        working_directory = [string]$_.WorkingDirectory
    }
})
$triggers = @($task.Triggers | ForEach-Object {
    [pscustomobject]@{
        start_boundary = [string]$_.StartBoundary
        enabled = $_.Enabled
        repetition_interval = [string]$_.Repetition.Interval
        repetition_duration = [string]$_.Repetition.Duration
        stop_at_duration_end = $_.Repetition.StopAtDurationEnd
    }
})

$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$healthProperty = @("healthCheck", "health_check", "health") |
    Where-Object { $config.PSObject.Properties.Name -contains $_ } |
    Select-Object -First 1
$healthConfig = if ($healthProperty) { $config.$healthProperty } else { $null }
$service = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewProxy8093'" -ErrorAction SilentlyContinue

[pscustomobject]@{
    schema = "ops.8093.health-guard-runtime.readonly.v2"
    captured_at = (Get-Date).ToString("o")
    service = if ($service) {
        [pscustomobject]@{
            name = $service.Name
            state = $service.State
            start_mode = $service.StartMode
            process_id = $service.ProcessId
            path_name = $service.PathName
        }
    } else { $null }
    task = [pscustomobject]@{
        task_path = $task.TaskPath
        task_name = $task.TaskName
        state = [string]$task.State
        last_run_time = $taskInfo.LastRunTime
        last_task_result = $taskInfo.LastTaskResult
        next_run_time = $taskInfo.NextRunTime
        actions = $actions
        triggers = $triggers
        settings = [pscustomobject]@{
            multiple_instances = [string]$task.Settings.MultipleInstances
            restart_count = $task.Settings.RestartCount
            restart_interval = [string]$task.Settings.RestartInterval
            execution_time_limit = [string]$task.Settings.ExecutionTimeLimit
        }
    }
    health_script = [pscustomobject]@{
        path = $healthScriptPath
        exists = Test-Path -LiteralPath $healthScriptPath -PathType Leaf
        sha256 = (Get-FileHash -LiteralPath $healthScriptPath -Algorithm SHA256).Hash
        content = if ($IncludeScriptContent) { [IO.File]::ReadAllText($healthScriptPath, [Text.Encoding]::UTF8) } else { $null }
    }
    config = [pscustomobject]@{
        path = $configPath
        sha256 = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        top_level_keys = @($config.PSObject.Properties.Name)
        service_name = [string]$config.serviceName
        health_property = $healthProperty
        health = $healthConfig
    }
    service_config_files = @(
        Get-ChildItem -LiteralPath (Join-Path $projectRoot "tools\service_configs") -File -Filter "*.json" |
            Sort-Object Name |
            ForEach-Object {
                [pscustomobject]@{
                    name = $_.Name
                    sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
                }
            }
    )
    state = if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else { $null }
    health_log = [pscustomobject]@{
        path = $healthLogPath
        tail = if (Test-Path -LiteralPath $healthLogPath) {
            @(Get-Content -LiteralPath $healthLogPath -Tail 30 -Encoding UTF8 | ForEach-Object { [string]$_ })
        } else { @() }
    }
} | ConvertTo-Json -Depth 10
