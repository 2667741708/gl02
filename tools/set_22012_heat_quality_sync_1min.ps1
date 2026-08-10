$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $PSScriptRoot
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\HeatPerformanceQualitySync_1min_$stamp"
$backupXml = Join-Path $backupRoot 'task.before.xml'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

function Get-TaskActionSignature($Task) {
    return @($Task.Actions | ForEach-Object {
        "{0}|{1}|{2}" -f $_.Execute, $_.Arguments, $_.WorkingDirectory
    }) -join ';'
}

function Get-TaskPrincipalSignature($Task) {
    return "{0}|{1}|{2}" -f $Task.Principal.UserId, $Task.Principal.LogonType, $Task.Principal.RunLevel
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskInfoBefore = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
$wasEnabled = $task.State.ToString() -ne 'Disabled'
$actionBefore = Get-TaskActionSignature $task
$principalBefore = Get-TaskPrincipalSignature $task
$protectedBefore = [ordered]@{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $protectedBefore["port_$port"] = Get-ListenerPid $port
    if (-not $protectedBefore["port_$port"]) { throw "Protected port $port is not listening" }
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backupXmlText = Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName
[IO.File]::WriteAllText($backupXml, $backupXmlText, [Text.UTF8Encoding]::new($true))
$rollbackApplied = $false

try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    $next = (Get-Date).AddMinutes(1)
    $startAt = $next.Date.AddHours($next.Hour).AddMinutes($next.Minute).AddSeconds(35)
    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At $startAt `
        -RepetitionInterval (New-TimeSpan -Minutes 1) `
        -RepetitionDuration (New-TimeSpan -Days 3650)
    Set-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Trigger $trigger | Out-Null

    [xml]$currentXml = Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    $namespace = New-Object System.Xml.XmlNamespaceManager($currentXml.NameTable)
    $namespace.AddNamespace('t', $currentXml.DocumentElement.NamespaceURI)
    $policy = $currentXml.SelectSingleNode('/t:Task/t:Settings/t:MultipleInstancesPolicy', $namespace)
    if (-not $policy) { throw 'MultipleInstancesPolicy is absent from task XML' }
    $policy.InnerText = 'IgnoreNew'
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Xml $currentXml.OuterXml -Force | Out-Null
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null

    $configured = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    if ((Get-TaskActionSignature $configured) -ne $actionBefore) { throw 'Task action changed unexpectedly' }
    if ((Get-TaskPrincipalSignature $configured) -ne $principalBefore) { throw 'Task principal changed unexpectedly' }
    if ($configured.Settings.MultipleInstances.ToString() -ne 'IgnoreNew') { throw 'Task overlap policy is not IgnoreNew' }
    $interval = [Xml.XmlConvert]::ToTimeSpan([string]@($configured.Triggers)[0].Repetition.Interval)
    if ($interval -ne [TimeSpan]::FromMinutes(1)) { throw "Task interval is not one minute: $interval" }

    $protectedAfter = [ordered]@{}
    foreach ($port in @(8093, 8768, 8094, 8770)) {
        $protectedAfter["port_$port"] = Get-ListenerPid $port
        if ($protectedAfter["port_$port"] -ne $protectedBefore["port_$port"]) {
            throw "Protected PID changed on port $port"
        }
    }
} catch {
    $deploymentError = $_
    try {
        Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Xml $backupXmlText -Force | Out-Null
        if ($wasEnabled) {
            Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
        } else {
            Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
        }
        $rollbackApplied = $true
    } catch {
        Write-Warning "Task rollback failed: $($_.Exception.Message)"
    }
    throw $deploymentError
}

$taskInfoAfter = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
[ordered]@{
    schema = 'ops.heat-quality.schedule.v1'
    requirement_id = 'OPS-HEAT-QUALITY-1MIN-20260809'
    changed_at = (Get-Date).ToString('o')
    task_path = $taskPath
    task_name = $taskName
    previous_last_run_time = $taskInfoBefore.LastRunTime.ToString('o')
    next_run_time = $taskInfoAfter.NextRunTime.ToString('o')
    interval = 'PT1M'
    start_second = 35
    multiple_instances = $configured.Settings.MultipleInstances.ToString()
    action_preserved = (Get-TaskActionSignature $configured) -eq $actionBefore
    principal_preserved = (Get-TaskPrincipalSignature $configured) -eq $principalBefore
    backup_xml = $backupXml
    rollback_applied = $rollbackApplied
    protected_pids_before = $protectedBefore
    protected_pids_after = $protectedAfter
} | ConvertTo-Json -Depth 8
