[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.ToString() -ne '7.6.4') {
    throw 'This migration must run under PowerShell 7.6.4 Core.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ProtectedPorts = @(8093, 8094, 8095, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-residual-definitions" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Test-ProjectTask($Task, [string]$ActionText) {
    if ([string]$Task.TaskPath -match '^\\(?:BlastFurnace|GL02)') { return $true }
    if (("$($Task.TaskPath)$($Task.TaskName)") -match '^\\(?:BlastFurnace|GL02|CodexGL02)') { return $true }
    return $ActionText -like '*F:\高炉炼铁项目*'
}

function Get-StateName($Task) {
    switch ([int]$Task.State) {
        1 { return 'Disabled' }
        2 { return 'Queued' }
        3 { return 'Ready' }
        4 { return 'Running' }
        default { return "Unknown:$([int]$Task.State)" }
    }
}

function Get-PayloadFile([string]$Arguments) {
    $match = [regex]::Match($Arguments, '(?i)(?:^|\s)-File\s+(?:"([^"]+)"|([^\s]+))')
    if (-not $match.Success) { return $null }
    if ($match.Groups[1].Success) { return $match.Groups[1].Value }
    return $match.Groups[2].Value
}

function Assert-Syntax([string]$Path) {
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "PowerShell parse failed for ${Path}: $($errors[0].Message)" }
}

function New-PreservedAction([string]$Arguments, [string]$WorkingDirectory) {
    $desired = $Arguments -replace '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
    $desired = $desired -replace '(?i)^\s*-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
    if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        return New-ScheduledTaskAction -Execute $PwshPath -Argument $desired
    }
    return New-ScheduledTaskAction -Execute $PwshPath -Argument $desired -WorkingDirectory $WorkingDirectory
}

function Get-Listeners {
    $map = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $map[[string]$port] = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object)
    }
    return $map
}

$BeforeListeners = Get-Listeners
$Candidates = [Collections.Generic.List[object]]::new()
foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) { continue }
    $action = $actions[0]
    $leaf = [IO.Path]::GetFileName(([string]$action.Execute).Trim('"'))
    if ($leaf -inotmatch '^powershell(?:\.exe)?$') { continue }
    $text = "$($action.Execute) $($action.Arguments) $($action.WorkingDirectory)"
    if (-not (Test-ProjectTask $task $text)) { continue }
    if ((Get-StateName $task) -eq 'Running') { throw "Residual legacy task is Running: $($task.TaskPath)$($task.TaskName)" }
    $payload = Get-PayloadFile ([string]$action.Arguments)
    $payloadExists = $payload -and (Test-Path -LiteralPath $payload -PathType Leaf)
    if ($payloadExists) { Assert-Syntax $payload }
    $Candidates.Add([ordered]@{
        task = $task
        action = $action
        payload = $payload
        payload_exists = [bool]$payloadExists
    })
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$Results = [Collections.Generic.List[object]]::new()
foreach ($candidate in $Candidates) {
    $task = $candidate.task
    $action = $candidate.action
    $identity = "$($task.TaskPath)$($task.TaskName)"
    $safeName = ($identity -replace '[^A-Za-z0-9_.-]', '_').Trim('_')
    $xmlPath = Join-Path $BackupRoot "$safeName.xml"
    [IO.File]::WriteAllText($xmlPath, (Export-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName), $Utf8NoBom)
    $payload = $candidate.payload
    $payloadExists = [bool]$candidate.payload_exists
    $newAction = New-PreservedAction ([string]$action.Arguments) ([string]$action.WorkingDirectory)
    Set-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName -Action $newAction | Out-Null
    $after = Get-ScheduledTask -TaskPath $task.TaskPath -TaskName $task.TaskName
    if ([string](@($after.Actions)[0].Execute) -ine $PwshPath) { throw "Residual task migration failed: $identity" }
    $Results.Add([ordered]@{
        identity = $identity
        state = Get-StateName $after
        payload = $payload
        payload_exists = [bool]$payloadExists
        payload_syntax_checked = [bool]$payloadExists
        backup_xml = $xmlPath
        started = $false
        action_after = [string](@($after.Actions)[0].Execute)
    })
}

$ServiceName = 'BFBaselineProxy8092'
$ServicePath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
$Service = Get-Service -Name $ServiceName -ErrorAction Stop
if ($Service.Status -ne 'Stopped' -or $Service.StartType -ne 'Disabled') { throw 'BFBaselineProxy8092 is not a disabled residual service.' }
$Registry = Get-ItemProperty -LiteralPath $ServicePath -ErrorAction Stop
$ServiceBefore = [ordered]@{
    application = [string]$Registry.Application
    app_parameters = [string]$Registry.AppParameters
    app_directory = [string]$Registry.AppDirectory
}
[IO.File]::WriteAllText((Join-Path $BackupRoot 'BFBaselineProxy8092.registry.before.json'), ($ServiceBefore | ConvertTo-Json -Depth 4), $Utf8NoBom)
if ([string]$Registry.Application -ine $PwshPath) {
    Set-ItemProperty -LiteralPath $ServicePath -Name Application -Value $PwshPath -Type String
}
$ServiceAfter = Get-ItemProperty -LiteralPath $ServicePath -ErrorAction Stop
if ([string]$ServiceAfter.Application -ine $PwshPath) { throw 'Disabled residual service migration failed.' }

$AfterListeners = Get-Listeners
foreach ($port in $ProtectedPorts) {
    $key = [string]$port
    if ((@($BeforeListeners[$key]) -join ',') -cne (@($AfterListeners[$key]) -join ',')) {
        throw "Protected listener changed unexpectedly: $port"
    }
}

[ordered]@{
    schema = 'ops.22012.residual-pwsh7-definitions.migration.result.v1'
    ok = $true
    backup = $BackupRoot
    task_count = $Results.Count
    tasks = @($Results)
    disabled_service = [ordered]@{
        name = $ServiceName
        state = $Service.Status.ToString()
        start_type = $Service.StartType.ToString()
        application_before = $ServiceBefore.application
        application_after = [string]$ServiceAfter.Application
        started = $false
    }
    protected_before = $BeforeListeners
    protected_after = $AfterListeners
} | ConvertTo-Json -Depth 12
