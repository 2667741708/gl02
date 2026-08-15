param()

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ApiTimeoutSeconds = 30
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
    param([int]$Port, [array]$Listeners)
    $portListeners = @($Listeners | Where-Object { $_.LocalPort -eq $Port })
    return [ordered]@{
        port = $Port
        listening = $portListeners.Count -gt 0
        process_ids = @($portListeners | Select-Object -ExpandProperty OwningProcess -Unique)
    }
}

function Convert-ApiSummary {
    param([string]$Name, $Body)
    if ($Name -like '*strict_status') {
        $slot = $Body.current_slot
        return [ordered]@{
            schema = $Body.schema
            status = $Body.status
            current_slot = [ordered]@{
                schedule_slot_ts = $slot.schedule_slot_ts
                slot_status = $slot.slot_status
                attempt_count = $slot.attempt_count
                prediction_id = $slot.prediction_id
                completed_at = $slot.completed_at
                last_error = $slot.last_error
            }
            model = [ordered]@{
                schema = $Body.model.schema
                name = $Body.model.name
                sha256 = $Body.model.sha256
                feature_count = $Body.model.feature_count
            }
            contracts = $Body.contracts
        }
    }
    if ($Name -like '*hourly_table') {
        return [ordered]@{
            schema = $Body.schema
            status = $Body.status
            count = $Body.count
            metrics = $Body.metrics
            items = @($Body.items | Select-Object -First 1)
        }
    }
    $latestActual = @($Body.targets | Where-Object { $null -ne $_.si_avg } | Select-Object -First 1)
    return [ordered]@{
        schema = $Body.schema
        status = $Body.status
        latest_actual = @($latestActual)
        candidate_targets = @($Body.candidate_targets | Select-Object -First 5)
        model = $Body.model
        audit_table_ready = $Body.audit_table_ready
    }
}

function Read-ApiOnce {
    param($Request, [int]$Attempt)
    $client = [Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds($ApiTimeoutSeconds)
    try {
        try {
            $response = $client.GetAsync([string]$Request.uri).GetAwaiter().GetResult()
            if (-not $response.IsSuccessStatusCode) {
                throw "HTTP $([int]$response.StatusCode) $($response.ReasonPhrase)"
            }
            $content = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $body = $content | ConvertFrom-Json -Depth 20
            return [ordered]@{
                name = $Request.name
                ok = $true
                attempt_count = $Attempt
                body = Convert-ApiSummary -Name $Request.name -Body $body
            }
        }
        catch {
            return [ordered]@{
                name = $Request.name
                ok = $false
                attempt_count = $Attempt
                error = $_.Exception.Message
            }
        }
    }
    finally {
        $client.Dispose()
    }
}

function Read-Apis {
    param([array]$Specs)
    $firstPass = @()
    foreach ($request in $Specs) {
        $firstPass += ,(Read-ApiOnce -Request $request -Attempt 1)
    }

    $results = @()
    for ($index = 0; $index -lt $Specs.Count; $index++) {
        $first = $firstPass[$index]
        if ($first.ok) {
            $results += ,$first
            continue
        }
        $retry = Read-ApiOnce -Request $Specs[$index] -Attempt 2
        $retry['initial_error'] = $first.error
        $results += ,$retry
    }
    return @($results)
}

$tasks = @(
    Read-TaskState -TaskPath '\GL02SensorSync\' -TaskName 'IMESRealtime'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'HeatPerformanceQualitySync'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20StrictHourlyPrediction'
    Read-TaskState -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction'
)

$allListeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
$ports = @(8093, 8094, 8768, 8770, 5432 | ForEach-Object {
    Read-PortState -Port $_ -Listeners $allListeners
})

$apiSpecs = @(
    [pscustomobject]@{ name = '8093_status'; uri = 'http://127.0.0.1:8093/api/si-v20/status' }
    [pscustomobject]@{ name = '8093_strict_status'; uri = 'http://127.0.0.1:8093/api/si-v20/strict-hourly/status' }
    [pscustomobject]@{ name = '8093_hourly_table'; uri = 'http://127.0.0.1:8093/api/si-v20/hourly-table?limit=24' }
    [pscustomobject]@{ name = '8094_status'; uri = 'http://127.0.0.1:8094/api/si-v20/status' }
    [pscustomobject]@{ name = '8094_strict_status'; uri = 'http://127.0.0.1:8094/api/si-v20/strict-hourly/status' }
    [pscustomobject]@{ name = '8094_hourly_table'; uri = 'http://127.0.0.1:8094/api/si-v20/hourly-table?limit=24' }
)
$apis = @(Read-Apis -Specs $apiSpecs)

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
