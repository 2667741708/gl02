param()

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required'
}

function Read-TaskState {
    param([string]$TaskPath, [string]$TaskName)
    try {
        $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
        $action = @($task.Actions)[0]
        return [ordered]@{
            task_path = $TaskPath
            task_name = $TaskName
            state = [string]$task.State
            last_run_time = $info.LastRunTime
            last_task_result = $info.LastTaskResult
            next_run_time = $info.NextRunTime
            action_execute = $action.Execute
            action_arguments = $action.Arguments
            uses_legacy_windows_powershell = [bool](
                [IO.Path]::GetFileName([string]$action.Execute) -ieq 'powershell.exe'
            )
        }
    }
    catch {
        return [ordered]@{
            task_path = $TaskPath
            task_name = $TaskName
            state = 'missing'
            error = $_.Exception.Message
        }
    }
}

function Read-PortState {
    param([int]$Port)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    return [ordered]@{
        port = $Port
        listening = $listeners.Count -gt 0
        process_ids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    }
}

function Read-Api {
    param([string]$Name, [string]$Uri)
    try {
        $body = Invoke-RestMethod -UseBasicParsing -Uri $Uri -TimeoutSec 30
        if ($Name -like '*strict_status') {
            $summary = [ordered]@{
                schema = $body.schema
                status = $body.status
                current_slot = $body.current_slot
                model = $body.model
                contracts = $body.contracts
            }
        }
        elseif ($Name -like '*hourly_table') {
            $summary = [ordered]@{
                schema = $body.schema
                status = $body.status
                count = $body.count
                metrics = $body.metrics
                items = @($body.items | Select-Object -First 24)
            }
        }
        else {
            $latestActual = @($body.targets | Where-Object { $null -ne $_.si_avg } | Select-Object -First 1)
            $summary = [ordered]@{
                schema = $body.schema
                status = $body.status
                latest_actual = @($latestActual)
                candidate_targets = @($body.candidate_targets | Select-Object -First 5)
                model = $body.model
                audit_table_ready = $body.audit_table_ready
            }
        }
        return [ordered]@{ name = $Name; ok = $true; body = $summary }
    }
    catch {
        return [ordered]@{ name = $Name; ok = $false; error = $_.Exception.Message }
    }
}

$tasks = @(
    Read-TaskState -TaskPath '\GL02SensorSync\' -TaskName 'IMESRealtime'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'HeatPerformanceQualitySync'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20StrictHourlyPrediction'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction'
)

$ports = @(8093, 8094, 8768, 8770, 5432 | ForEach-Object { Read-PortState -Port $_ })

$apis = @(
    Read-Api -Name '8093_status' -Uri 'http://127.0.0.1:8093/api/si-v20/status'
    Read-Api -Name '8093_strict_status' -Uri 'http://127.0.0.1:8093/api/si-v20/strict-hourly/status'
    Read-Api -Name '8093_hourly_table' -Uri 'http://127.0.0.1:8093/api/si-v20/hourly-table'
    Read-Api -Name '8094_status' -Uri 'http://127.0.0.1:8094/api/si-v20/status'
    Read-Api -Name '8094_strict_status' -Uri 'http://127.0.0.1:8094/api/si-v20/strict-hourly/status'
    Read-Api -Name '8094_hourly_table' -Uri 'http://127.0.0.1:8094/api/si-v20/hourly-table'
)

$missingTasks = @($tasks | Where-Object { $_.state -eq 'missing' })
$legacyTaskActions = @($tasks | Where-Object {
    $_.task_name -ne 'IMESRealtime' -and $_.uses_legacy_windows_powershell
})
$result = [ordered]@{
    ok = (@($ports | Where-Object { -not $_.listening }).Count -eq 0) -and
         (@($apis | Where-Object { -not $_.ok }).Count -eq 0) -and
         ($missingTasks.Count -eq 0) -and
         ($legacyTaskActions.Count -eq 0)
    schema = 'ops.si-v20.new-heat-remote-acceptance-probe.v1'
    checked_at = Get-Date
    powershell = [ordered]@{
        edition = $PSVersionTable.PSEdition
        version = $PSVersionTable.PSVersion.ToString()
    }
    ports = $ports
    tasks = $tasks
    legacy_task_actions = @($legacyTaskActions | Select-Object task_path, task_name, action_execute)
    apis = $apis
}

$result | ConvertTo-Json -Depth 12
