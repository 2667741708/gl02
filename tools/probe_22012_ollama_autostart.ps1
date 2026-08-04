$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Get-RelevantEnvironment {
    param([object]$Value)

    $items = @()
    if ($null -eq $Value) {
        return $items
    }
    foreach ($entry in @($Value)) {
        $text = [string]$entry
        if ($text -match '^(OLLAMA_|BF_LLM_MODEL=|BF_PUBLIC_MODEL|BF_PROXY_PORT=|PORT=)') {
            $items += $text
        }
    }
    return $items
}

function Get-ServiceEvidence {
    $rows = @()
    foreach ($service in @(Get-CimInstance Win32_Service)) {
        $parametersPath = "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\$($service.Name)\Parameters"
        $parameters = $null
        if (Test-Path -LiteralPath $parametersPath) {
            $parameters = Get-ItemProperty -LiteralPath $parametersPath -ErrorAction SilentlyContinue
        }
        $application = if ($parameters) { [string]$parameters.Application } else { "" }
        $appParameters = if ($parameters) { [string]$parameters.AppParameters } else { "" }
        $appDirectory = if ($parameters) { [string]$parameters.AppDirectory } else { "" }
        $appEnvironment = if ($parameters) { Get-RelevantEnvironment $parameters.AppEnvironmentExtra } else { @() }
        $combined = @(
            $service.Name,
            $service.DisplayName,
            $service.PathName,
            $application,
            $appParameters,
            $appDirectory,
            ($appEnvironment -join " ")
        ) -join " "
        if ($combined -notmatch '(?i)ollama|blastfurnace|bfv[34]|11434|chiqiong|diagnosis-runtime|service_configs') {
            continue
        }
        $rows += [pscustomobject]@{
            name = $service.Name
            display_name = $service.DisplayName
            state = $service.State
            start_mode = $service.StartMode
            process_id = $service.ProcessId
            service_path = $service.PathName
            nssm_application = $application
            nssm_parameters = $appParameters
            nssm_directory = $appDirectory
            relevant_environment = @($appEnvironment)
        }
    }
    return $rows
}

function Get-TaskEvidence {
    $rows = @()
    foreach ($task in @(Get-ScheduledTask -ErrorAction SilentlyContinue)) {
        $actions = @()
        foreach ($action in @($task.Actions)) {
            $actions += [pscustomobject]@{
                execute = [string]$action.Execute
                arguments = [string]$action.Arguments
                working_directory = [string]$action.WorkingDirectory
            }
        }
        $actionText = ($actions | ConvertTo-Json -Depth 4 -Compress)
        $combined = "$($task.TaskPath)$($task.TaskName) $actionText"
        if ($combined -notmatch '(?i)ollama|blastfurnace|bfv[34]|11434|chiqiong|diagnosis-runtime|managed_services|service_configs') {
            continue
        }
        $info = $null
        try {
            $info = Get-ScheduledTaskInfo -TaskName $task.TaskName -TaskPath $task.TaskPath -ErrorAction Stop
        } catch {
        }
        $rows += [pscustomobject]@{
            task_path = $task.TaskPath
            task_name = $task.TaskName
            state = [string]$task.State
            enabled = [bool]$task.Settings.Enabled
            last_run_time = if ($info) { $info.LastRunTime } else { $null }
            last_task_result = if ($info) { $info.LastTaskResult } else { $null }
            next_run_time = if ($info) { $info.NextRunTime } else { $null }
            actions = $actions
        }
    }
    return $rows
}

function Get-ProcessEvidence {
    $processes = @(Get-CimInstance Win32_Process)
    $byPid = @{}
    foreach ($process in $processes) {
        $byPid[[int]$process.ProcessId] = $process
    }
    $rows = @()
    foreach ($process in $processes) {
        $combined = "$($process.Name) $($process.ExecutablePath) $($process.CommandLine)"
        if ($combined -notmatch '(?i)ollama|start_v3_8092|ollama_proxy_server|run_22012_8094|11434|chiqiong|diagnosis-runtime') {
            continue
        }
        $parent = $byPid[[int]$process.ParentProcessId]
        $rows += [pscustomobject]@{
            pid = $process.ProcessId
            parent_pid = $process.ParentProcessId
            name = $process.Name
            executable = $process.ExecutablePath
            command_line = $process.CommandLine
            creation_date = $process.CreationDate
            parent_name = if ($parent) { $parent.Name } else { $null }
            parent_command_line = if ($parent) { $parent.CommandLine } else { $null }
        }
    }
    return $rows
}

function Get-ListenerEvidence {
    $rows = @()
    $connections = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
    foreach ($connection in $connections) {
        if (
            ($connection.LocalPort -ge 11430 -and $connection.LocalPort -le 11440) -or
            ($connection.LocalPort -in @(8092, 8093, 8094))
        ) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
            $rows += [pscustomobject]@{
                address = $connection.LocalAddress
                port = $connection.LocalPort
                pid = $connection.OwningProcess
                process_name = if ($process) { $process.Name } else { $null }
                command_line = if ($process) { $process.CommandLine } else { $null }
            }
        }
    }
    return $rows
}

function Convert-HealthPost {
    param([object]$Health)

    $rows = @()
    if (-not $Health -or -not $Health.httpPost) {
        return $rows
    }
    foreach ($post in @($Health.httpPost)) {
        $json = $post.json
        $rows += [pscustomobject]@{
            url = [string]$post.url
            model = if ($json) { [string]$json.model } else { "" }
            keep_alive = if ($json) { [string]$json.keep_alive } else { "" }
            stream = if ($json -and $json.PSObject.Properties.Name -contains "stream") { [bool]$json.stream } else { $null }
        }
    }
    return $rows
}

function Get-ConfigEvidence {
    $roots = @(
        "F:\高炉炼铁项目-real-sensor-v2_V3",
        "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
    )
    $rows = @()
    foreach ($root in $roots) {
        $configDirectory = Join-Path $root "tools\service_configs"
        if (-not (Test-Path -LiteralPath $configDirectory)) {
            continue
        }
        foreach ($file in @(Get-ChildItem -LiteralPath $configDirectory -File -Filter "*.json" -ErrorAction SilentlyContinue)) {
            try {
                $json = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            } catch {
                continue
            }
            $selectedEnvironment = [ordered]@{}
            if ($json.env) {
                foreach ($property in @($json.env.PSObject.Properties)) {
                    if ($property.Name -match '^(OLLAMA_|BF_LLM_MODEL$|BF_PUBLIC_MODEL|BF_PROXY_PORT$|PORT$)') {
                        $selectedEnvironment[$property.Name] = [string]$property.Value
                    }
                }
            }
            $combined = @(
                $file.Name,
                [string]$json.serviceName,
                [string]$json.executable,
                [string]$json.arguments,
                ($selectedEnvironment | ConvertTo-Json -Compress),
                ((Convert-HealthPost $json.health) | ConvertTo-Json -Compress)
            ) -join " "
            if ($combined -notmatch '(?i)ollama|11434|chiqiong|diagnosis-runtime|bf_llm_model') {
                continue
            }
            $rows += [pscustomobject]@{
                path = $file.FullName
                last_write_time = $file.LastWriteTime
                service_name = [string]$json.serviceName
                executable = [string]$json.executable
                arguments = [string]$json.arguments
                working_directory = [string]$json.workingDirectory
                relevant_environment = $selectedEnvironment
                health_http_post = @(Convert-HealthPost $json.health)
            }
        }
    }
    return $rows
}

function Get-ScriptReferenceEvidence {
    $roots = @(
        "F:\高炉炼铁项目-real-sensor-v2_V3\tools",
        "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools"
    )
    $rows = @()
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        $files = @(Get-ChildItem -LiteralPath $root -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".ps1", ".cmd", ".bat", ".py", ".json", ".yaml", ".yml") })
        foreach ($file in $files) {
            if ($file.Length -gt 2MB) {
                continue
            }
            $matches = @(Select-String -LiteralPath $file.FullName -Pattern @(
                "chiqiong-blast-furnace",
                "bf-diagnosis-runtime",
                "BFOllama11434",
                "ollama.exe serve",
                "OLLAMA_HOST",
                "OLLAMA_KEEP_ALIVE"
            ) -SimpleMatch -ErrorAction SilentlyContinue)
            if ($matches.Count -eq 0) {
                continue
            }
            $rows += [pscustomobject]@{
                path = $file.FullName
                matches = @($matches | Select-Object -First 40 | ForEach-Object {
                    [pscustomobject]@{
                        line_number = $_.LineNumber
                        line = $_.Line.Trim()
                    }
                })
            }
        }
    }
    return $rows
}

function Get-OllamaEndpointEvidence {
    $result = [ordered]@{}
    foreach ($endpoint in @("version", "tags", "ps")) {
        try {
            $result[$endpoint] = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/$endpoint" -TimeoutSec 3
        } catch {
            $result[$endpoint] = [pscustomobject]@{ error = $_.Exception.Message }
        }
    }
    return $result
}

[pscustomobject]@{
    collected_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
    computer_name = $env:COMPUTERNAME
    services = @(Get-ServiceEvidence)
    scheduled_tasks = @(Get-TaskEvidence)
    listeners = @(Get-ListenerEvidence)
    processes = @(Get-ProcessEvidence)
    service_configs = @(Get-ConfigEvidence)
    script_references = @(Get-ScriptReferenceEvidence)
    ollama = Get-OllamaEndpointEvidence
} | ConvertTo-Json -Depth 20
