[CmdletBinding()]
param(
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This audit requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ProgressPreference = 'SilentlyContinue'

trap {
    [ordered]@{
        schema = 'ops.22012.project-powershell-runtime-audit.error.v1'
        ok = $false
        message = $_.Exception.Message
        script_line = $_.InvocationInfo.ScriptLineNumber
        line = $_.InvocationInfo.Line
        position = $_.InvocationInfo.PositionMessage
    } | ConvertTo-Json -Depth 5
    exit 1
}

$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$DefaultRemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
if (-not $OutputPath -and (Test-Path -LiteralPath $DefaultRemoteRoot -PathType Container)) {
    $OutputPath = Join-Path $DefaultRemoteRoot 'logs\pwsh7_runtime_audit_latest.json'
}
$ProjectMarkers = @(
    'F:\高炉炼铁项目',
    '\BlastFurnace',
    '\GL02',
    'BFV4Preview',
    'V3AutoPreview',
    'auto_diagnosis',
    'heat_performance',
    'si_v20'
)

function Test-ProjectOwned([string]$Text, [string]$Identity) {
    if ($Identity -match '^\\(?:BlastFurnace|GL02)') { return $true }
    if ($Identity -match '^(?:BFV|BFOllama|BFHeat|GL02|V3AutoPreview)') { return $true }
    foreach ($marker in $ProjectMarkers) {
        if ($Text.IndexOf($marker, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

function Get-IndirectWrapper([string]$Executable, [string]$Arguments) {
    if ([IO.Path]::GetFileName($Executable) -ine 'wscript.exe') { return $null }
    $match = [regex]::Match($Arguments, '["'']([^"'']+\.vbs)["'']', 'IgnoreCase')
    if (-not $match.Success) { return $null }
    $path = $match.Groups[1].Value
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return [ordered]@{ path = $path; exists = $false; runtime_class = 'IndirectWrapperMissing'; sha256 = $null }
    }
    $content = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    $class = if ($content -match '(?i)pwsh\.exe') {
        'AlreadyPwsh7Indirect'
    } elseif ($content -match '(?i)(?:WindowsPowerShell\\v1\.0\\)?powershell\.exe') {
        'LegacyPS5Indirect'
    } else {
        'IndirectWrapperUnknown'
    }
    return [ordered]@{
        path = $path
        exists = $true
        runtime_class = $class
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    }
}

function Get-RuntimeClass([string]$Executable, [string]$Text) {
    $leaf = [IO.Path]::GetFileName($Executable)
    if ($leaf -ieq 'pwsh.exe') { return 'AlreadyPwsh7' }
    if ($leaf -ieq 'powershell.exe' -or $Text -match '(?i)WindowsPowerShell\\v1\.0\\powershell\.exe') {
        return 'LegacyPS5'
    }
    if ($Text -match '(?i)(?:^|[\s"''])powershell(?:\.exe)?(?:[\s"'']|$)') { return 'LegacyPS5' }
    return 'NoPowerShellWrapper'
}

function Protect-ArgumentText([string]$Text) {
    if (-not $Text) { return '' }
    $protected = $Text -replace '(?i)(password|pwd|token|secret)(\s*[=:]\s*)([^\s"'']+)', '$1$2<redacted>'
    return $protected
}

function Convert-DateToIso($Value) {
    if ($null -eq $Value) { return $null }
    return ([datetime]$Value).ToString('o')
}

function Get-StateName($State) {
    switch ([int]$State) {
        1 { return 'Disabled' }
        2 { return 'Queued' }
        3 { return 'Ready' }
        4 { return 'Running' }
        default { return $State.ToString() }
    }
}

function Get-PayloadFile([string]$Arguments) {
    $match = [regex]::Match($Arguments, '(?i)(?:^|\s)-File\s+(?:"([^"]+)"|([^\s]+))')
    if (-not $match.Success) { return $null }
    $path = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
    return [ordered]@{
        path = $path
        exists = Test-Path -LiteralPath $path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $path -PathType Leaf) {
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        } else { $null }
    }
}

$TaskRecords = [System.Collections.Generic.List[object]]::new()
foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
    $actions = @($task.Actions | ForEach-Object {
        [ordered]@{
            execute = [string]$_.Execute
            arguments = Protect-ArgumentText ([string]$_.Arguments)
            working_directory = [string]$_.WorkingDirectory
        }
    })
    $identity = "$($task.TaskPath)$($task.TaskName)"
    $actionText = ($actions | ConvertTo-Json -Depth 4 -Compress)
    if (-not (Test-ProjectOwned $actionText $identity)) { continue }
    $info = Get-ScheduledTaskInfo -TaskPath $task.TaskPath -TaskName $task.TaskName -ErrorAction SilentlyContinue
    $stateName = Get-StateName $task.State
    $triggerRecords = @($task.Triggers | ForEach-Object {
        [ordered]@{
            type = $_.CimClass.CimClassName
            enabled = [bool]$_.Enabled
            start_boundary = [string]$_.StartBoundary
            end_boundary = [string]$_.EndBoundary
            repetition_interval = [string]$_.Repetition.Interval
            repetition_duration = [string]$_.Repetition.Duration
        }
    })
    $classes = @($actions | ForEach-Object {
        $indirect = Get-IndirectWrapper ([string]$_.execute) ([string]$_.arguments)
        if ($indirect) { $indirect.runtime_class } else {
            Get-RuntimeClass ([string]$_.execute) ("$($_.execute) $($_.arguments)")
        }
    } | Sort-Object -Unique)
    $wrappers = @($actions | ForEach-Object {
        Get-IndirectWrapper ([string]$_.execute) ([string]$_.arguments)
    } | Where-Object { $null -ne $_ })
    $TaskRecords.Add([ordered]@{
        identity = $identity
        task_path = $task.TaskPath
        task_name = $task.TaskName
        state = $stateName
        enabled = $stateName -ne 'Disabled'
        runtime_class = if ($classes.Count -eq 1) { $classes[0] } else { 'Mixed' }
        actions = $actions
        indirect_wrappers = $wrappers
        payload_files = @($actions | ForEach-Object { Get-PayloadFile ([string]$_.arguments) } | Where-Object { $null -ne $_ })
        triggers = $triggerRecords
        last_run_time = if ($info) { Convert-DateToIso $info.LastRunTime } else { $null }
        last_task_result = if ($info) { [long]$info.LastTaskResult } else { $null }
        next_run_time = if ($info) { Convert-DateToIso $info.NextRunTime } else { $null }
    })
}

$ServiceRecords = [System.Collections.Generic.List[object]]::new()
foreach ($service in @(Get-CimInstance Win32_Service -ErrorAction Stop)) {
    $parametersPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$($service.Name)\Parameters"
    $application = ''
    $appParameters = ''
    $appDirectory = ''
    if (Test-Path -LiteralPath $parametersPath) {
        $parameters = Get-ItemProperty -LiteralPath $parametersPath -ErrorAction SilentlyContinue
        if ($parameters) {
            $application = [string]$parameters.Application
            $appParameters = Protect-ArgumentText ([string]$parameters.AppParameters)
            $appDirectory = [string]$parameters.AppDirectory
        }
    }
    $combined = "$($service.PathName) $application $appParameters $appDirectory"
    if (-not (Test-ProjectOwned $combined ([string]$service.Name))) { continue }
    $effectiveExecutable = if ($application) { $application } else { [string]$service.PathName }
    $ServiceRecords.Add([ordered]@{
        name = [string]$service.Name
        display_name = [string]$service.DisplayName
        state = [string]$service.State
        start_mode = [string]$service.StartMode
        process_id = [int]$service.ProcessId
        runtime_class = Get-RuntimeClass $effectiveExecutable $combined
        service_path = Protect-ArgumentText ([string]$service.PathName)
        application = $application
        app_parameters = $appParameters
        app_directory = $appDirectory
        payload_file = Get-PayloadFile $appParameters
    })
}

$TaskSummary = [ordered]@{}
foreach ($class in @('LegacyPS5', 'LegacyPS5Indirect', 'AlreadyPwsh7', 'AlreadyPwsh7Indirect', 'NoPowerShellWrapper', 'IndirectWrapperMissing', 'IndirectWrapperUnknown', 'Mixed')) {
    $TaskSummary[$class] = @($TaskRecords | Where-Object { $_.runtime_class -eq $class }).Count
}
$ServiceSummary = [ordered]@{}
foreach ($class in @('LegacyPS5', 'AlreadyPwsh7', 'NoPowerShellWrapper', 'Mixed')) {
    $ServiceSummary[$class] = @($ServiceRecords | Where-Object { $_.runtime_class -eq $class }).Count
}

$RuntimeProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    [string]$_.Name -in @('powershell.exe', 'pwsh.exe') -and
    (Test-ProjectOwned ([string]$_.CommandLine) ([string]$_.Name))
} | ForEach-Object {
    [ordered]@{
        pid = [int]$_.ProcessId
        parent_pid = [int]$_.ParentProcessId
        name = [string]$_.Name
        runtime_class = if ([string]$_.Name -ieq 'pwsh.exe') { 'AlreadyPwsh7' } else { 'LegacyPS5' }
        command_line = Protect-ArgumentText ([string]$_.CommandLine)
    }
})
$ProcessSummary = [ordered]@{
    LegacyPS5 = @($RuntimeProcesses | Where-Object { $_.runtime_class -eq 'LegacyPS5' }).Count
    AlreadyPwsh7 = @($RuntimeProcesses | Where-Object { $_.runtime_class -eq 'AlreadyPwsh7' }).Count
}

$Report = [ordered]@{
    schema = 'ops.22012.project-powershell-runtime-audit.v1'
    audited_at = (Get-Date).ToString('o')
    read_only = $true
    host = $env:COMPUTERNAME
    current_process = [Environment]::ProcessPath
    current_edition = $PSVersionTable.PSEdition
    current_version = $PSVersionTable.PSVersion.ToString()
    pwsh_path = $PwshPath
    pwsh_exists = Test-Path -LiteralPath $PwshPath -PathType Leaf
    task_summary = $TaskSummary
    service_summary = $ServiceSummary
    process_summary = $ProcessSummary
    tasks = @($TaskRecords | Sort-Object identity)
    services = @($ServiceRecords | Sort-Object name)
    runtime_processes = @($RuntimeProcesses | Sort-Object pid)
}
$ReportJson = $Report | ConvertTo-Json -Depth 12
if ($OutputPath) {
    $outputParent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Path $outputParent -Force | Out-Null
    Set-Content -LiteralPath $OutputPath -Value $ReportJson -Encoding UTF8
    [ordered]@{
        schema = 'ops.22012.project-powershell-runtime-audit.pointer.v1'
        ok = $true
        production_state_mutated = $false
        audit_log_written = $true
        output_path = $OutputPath
        output_sha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
        task_summary = $TaskSummary
        service_summary = $ServiceSummary
        process_summary = $ProcessSummary
    } | ConvertTo-Json -Depth 5
} else {
    $ReportJson
}
