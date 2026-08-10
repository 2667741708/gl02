$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$requirementId = 'OPS-IMES-REALTIME-1MIN-20260809'
$root = Split-Path -Parent $PSScriptRoot
$taskPath = '\GL02SensorSync\'
$taskName = 'IMESRealtime'
$python = 'C:\Program Files\Python311\python.exe'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\IMESRealtime_1min_$stamp"
$backupXml = Join-Path $backupRoot 'IMESRealtime.before.xml'
$auditPython = Join-Path ([IO.Path]::GetTempPath()) "audit_imes_realtime_$stamp.py"

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

function Invoke-MirrorAudit {
    $raw = & $python -X utf8 $auditPython
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL mirror freshness audit failed' }
    return ($raw | ConvertFrom-Json)
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3.11 is unavailable' }
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskInfoBefore = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
$wasEnabled = $task.State.ToString() -ne 'Disabled'
$actionBefore = Get-TaskActionSignature $task
$principalBefore = Get-TaskPrincipalSignature $task
$oldInterval = @($task.Triggers)[0].Repetition.Interval
$protectedBefore = [ordered]@{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $pidValue = Get-ListenerPid $port
    if (-not $pidValue) { throw "Protected port $port is not listening" }
    $protectedBefore["port_$port"] = $pidValue
}

$auditSource = @'
import json
import os
from datetime import date, datetime
from decimal import Decimal
import psycopg
from psycopg.rows import dict_row

def default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)

password = os.environ.get("GL02_PGPASSWORD")
if not password:
    raise RuntimeError("GL02_PGPASSWORD is unavailable")
params = {
    "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
    "port": int(os.environ.get("GL02_PGPORT", "5432")),
    "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
    "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
    "password": password,
    "connect_timeout": 5,
    "options": "-c default_transaction_read_only=on -c statement_timeout=15000",
}
with psycopg.connect(**params, row_factory=dict_row) as connection:
    row = connection.execute("""
        SELECT now() AS db_now,
               max(COALESCE(fetched_at, updated_at)) AS latest_mirrored_at,
               max(COALESCE(row_json->>'meltNo', row_json->>'meltno'))
                   FILTER (WHERE COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE '2#%')
                   AS max_meltno
          FROM bf_imes.raw_rows
         WHERE dataset_key IN (
                   'bf2_output_list_cond_data',
                   'bf2_heat_lab_list_cond_data_avg2',
                   'bf2_heat_lab_all_list_cond_data_avg2_new'
               )
    """).fetchone()
print(json.dumps(dict(row), default=default, ensure_ascii=False))
'@
[IO.File]::WriteAllText($auditPython, $auditSource, [Text.UTF8Encoding]::new($false))

foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
$env:PYTHONUTF8 = '1'

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$backupXmlText = Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName
[IO.File]::WriteAllText($backupXml, $backupXmlText, [Text.UTF8Encoding]::new($true))
$backupHash = (Get-FileHash -LiteralPath $backupXml -Algorithm SHA256).Hash
$mirrorBefore = Invoke-MirrorAudit
$rollbackApplied = $false

try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue

    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At (Get-Date).AddMinutes(1) `
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

    $configuredTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    if ((Get-TaskActionSignature $configuredTask) -ne $actionBefore) { throw 'Task action changed unexpectedly' }
    if ((Get-TaskPrincipalSignature $configuredTask) -ne $principalBefore) { throw 'Task principal changed unexpectedly' }
    if ($configuredTask.Settings.MultipleInstances.ToString() -ne 'IgnoreNew') {
        throw 'Task overlap policy is not IgnoreNew'
    }
    $newInterval = @($configuredTask.Triggers)[0].Repetition.Interval
    $newIntervalTimeSpan = [Xml.XmlConvert]::ToTimeSpan([string]$newInterval)
    if ($newIntervalTimeSpan -ne [TimeSpan]::FromMinutes(1)) {
        throw "Task repetition interval is not one minute: $newInterval"
    }

    $verificationBefore = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 500
        $configuredTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        $verificationAfter = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
        $newRunObserved = $verificationAfter.LastRunTime -gt $verificationBefore.LastRunTime
    } while (-not $newRunObserved -and [DateTime]::UtcNow -lt $deadline)
    if (-not $newRunObserved) {
        throw 'A new IMESRealtime run did not start in 10 seconds'
    }

    $mirrorAfter = Invoke-MirrorAudit
    $mirrorAgeSeconds = ([datetime]$mirrorAfter.db_now - [datetime]$mirrorAfter.latest_mirrored_at).TotalSeconds
    if ($mirrorAgeSeconds -gt 600) {
        throw "IMES mirror is stale after verification: $mirrorAgeSeconds seconds"
    }

    $nextDelaySeconds = ($verificationAfter.NextRunTime - (Get-Date)).TotalSeconds
    if ($nextDelaySeconds -gt 90) { throw "Next run is too far away: $nextDelaySeconds seconds" }

    $protectedAfter = [ordered]@{}
    foreach ($port in @(8093, 8768, 8094, 8770)) {
        $pidValue = Get-ListenerPid $port
        $protectedAfter["port_$port"] = $pidValue
        if ($pidValue -ne $protectedBefore["port_$port"]) { throw "Protected PID changed on port $port" }
    }
} catch {
    $deploymentError = $_
    try {
        Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
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
} finally {
    Remove-Item -LiteralPath $auditPython -Force -ErrorAction SilentlyContinue
}

[ordered]@{
    schema = 'ops.imes-realtime.schedule.v1'
    requirement_id = $requirementId
    changed_at = (Get-Date).ToString('o')
    backup_xml = $backupXml
    backup_sha256 = $backupHash
    rollback_applied = $rollbackApplied
    old_interval = $oldInterval.ToString()
    new_interval = $newInterval.ToString()
    multiple_instances = $configuredTask.Settings.MultipleInstances.ToString()
    task_state = $configuredTask.State.ToString()
    last_run_time = $verificationAfter.LastRunTime.ToString('o')
    verification_run_started = $newRunObserved
    verification_run_state = $configuredTask.State.ToString()
    previous_last_task_result = $taskInfoBefore.LastTaskResult
    next_run_time = $verificationAfter.NextRunTime.ToString('o')
    mirror_before = $mirrorBefore
    mirror_after = $mirrorAfter
    mirror_age_seconds = [math]::Round($mirrorAgeSeconds, 1)
    protected_pids_before = $protectedBefore
    protected_pids_after = $protectedAfter
} | ConvertTo-Json -Depth 10
