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
$PythonPath = 'C:\Program Files\Python311\python.exe'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$V3Root = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\OPS-22012-PWSH7-ALL-20260811'
$TaskPath = '\'
$TaskName = 'BlastFurnaceV3PgContinuousSync30s'
$Destinations = [ordered]@{
    hidden_launcher = Join-Path $V3Root 'tools\run_hidden_ps1.vbs'
    realtime_runner = Join-Path $V3Root 'db_sync_storage\run_realtime_sync_pg_bg.ps1'
    watchdog = Join-Path $V3Root 'db_sync_storage\src\sync_watchdog.py'
}
$Staged = [ordered]@{
    hidden_launcher = Join-Path $StageRoot 'run_hidden_ps1.vbs'
    realtime_runner = Join-Path $StageRoot 'run_realtime_sync_pg_bg.ps1'
    watchdog = Join-Path $StageRoot 'sync_watchdog.py'
}
$ProtectedPorts = @(8093, 8094, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-realtime-sync" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Get-Listeners {
    $map = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $map[[string]$port] = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object)
    }
    return $map
}

function Assert-ListenersUnchanged($Before, $After) {
    foreach ($port in $ProtectedPorts) {
        $key = [string]$port
        if ((@($Before[$key]) -join ',') -cne (@($After[$key]) -join ',')) {
            throw "Protected listener changed unexpectedly: $port"
        }
    }
}

function Install-Atomically([string]$Source, [string]$Destination) {
    $parent = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $temporary = "$Destination.$PID.pwsh7.tmp"
    $replaceBackup = "$Destination.$PID.pwsh7.replace.bak"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    try {
        if (Test-Path -LiteralPath $Destination -PathType Leaf) {
            [IO.File]::Replace($temporary, $Destination, $replaceBackup, $true)
        } else {
            [IO.File]::Move($temporary, $Destination)
        }
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
    }
}

function Get-ExactTask {
    $matches = @(Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue)
    if ($matches.Count -ne 1) { throw "Task identity mismatch: $TaskPath$TaskName" }
    return $matches[0]
}

function Wait-TaskRunning([int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ([int](Get-ExactTask).State -eq 4) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Realtime synchronization task did not become Running.'
}

function Get-RealtimeShells {
    return @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        [string]$_.Name -in @('powershell.exe', 'pwsh.exe') -and
        [string]$_.CommandLine -like '*-File*run_realtime_sync_pg_bg.ps1*'
    })
}

function Assert-NewPwshProcess {
    $matches = @(Get-RealtimeShells | Where-Object { [string]$_.Name -ieq 'pwsh.exe' })
    if ($matches.Count -ne 1) { throw "Expected one pwsh realtime runner; found $($matches.Count)" }
    return $matches[0]
}

foreach ($key in $Staged.Keys) {
    if (-not (Test-Path -LiteralPath $Staged[$key] -PathType Leaf)) { throw "Staged file missing: $($Staged[$key])" }
    if ($key -ne 'hidden_launcher' -and -not (Test-Path -LiteralPath $Destinations[$key] -PathType Leaf)) {
        throw "Destination missing: $($Destinations[$key])"
    }
}
$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($Staged.realtime_runner, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw "Realtime runner parse failed: $($errors[0].Message)" }
$compileOutput = @(& $PythonPath -m py_compile $Staged.watchdog 2>&1)
if ($LASTEXITCODE -ne 0) { throw "Watchdog Python compile failed: $($compileOutput -join ' ')" }

$BeforeListeners = Get-Listeners
$Task = Get-ExactTask
$Action = @($Task.Actions)[0]
if ([string]$Action.Arguments -notlike '*run_realtime_sync_pg_bg.ps1*') { throw 'Realtime task payload mismatch.' }
$OldShells = @(Get-RealtimeShells)
if ($OldShells.Count -ne 1 -or [string]$OldShells[0].Name -ine 'powershell.exe') {
    throw "Expected one legacy realtime runner; found $($OldShells.Count)"
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$TaskXml = Export-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
[IO.File]::WriteAllText((Join-Path $BackupRoot 'task_before.xml'), $TaskXml, $Utf8NoBom)
foreach ($key in $Destinations.Keys) {
    if (Test-Path -LiteralPath $Destinations[$key] -PathType Leaf) {
        Copy-Item -LiteralPath $Destinations[$key] -Destination (Join-Path $BackupRoot "$key.before") -Force
    } else {
        [IO.File]::WriteAllText((Join-Path $BackupRoot "$key.absent"), 'absent_before_migration', $Utf8NoBom)
    }
}

$rollbackApplied = $false
try {
    Stop-Process -Id ([int]$OldShells[0].ProcessId) -Force -ErrorAction Stop
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (Get-CimInstance Win32_Process -Filter "ProcessId=$($OldShells[0].ProcessId)" -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'Legacy realtime runner did not exit.' }
        Start-Sleep -Milliseconds 250
    }

    foreach ($key in $Destinations.Keys) { Install-Atomically $Staged[$key] $Destinations[$key] }
    $validation = @(& $PwshPath -NoLogo -NoProfile -File $Destinations.realtime_runner -ValidateOnly 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Realtime runner ValidateOnly failed: $($validation -join ' ')" }

    $desiredArguments = ([string]$Action.Arguments) -replace '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
    $newAction = New-ScheduledTaskAction -Execute $PwshPath -Argument $desiredArguments -WorkingDirectory ([string]$Action.WorkingDirectory)
    Set-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $newAction | Out-Null
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    Wait-TaskRunning
    $NewProcess = Assert-NewPwshProcess

    $logDeadline = [DateTime]::UtcNow.AddSeconds(120)
    $freshLog = $null
    do {
        $freshLog = Get-ChildItem -LiteralPath (Join-Path $V3Root 'db_sync_storage\logs') -Filter 'continuous_sync_pg_*.log' -File |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($freshLog -and $freshLog.LastWriteTime -ge (Get-Date).AddMinutes(-2)) { break }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $logDeadline)
    if (-not $freshLog -or $freshLog.LastWriteTime -lt (Get-Date).AddMinutes(-2)) { throw 'Realtime synchronization log did not advance.' }

    $AfterListeners = Get-Listeners
    Assert-ListenersUnchanged $BeforeListeners $AfterListeners
    [ordered]@{
        schema = 'ops.22012.realtime-sync-pwsh7-migration.result.v1'
        ok = $true
        backup = $BackupRoot
        rollback_applied = $false
        old_pid = [int]$OldShells[0].ProcessId
        new_pid = [int]$NewProcess.ProcessId
        task_execute = [string](@((Get-ExactTask).Actions)[0].Execute)
        latest_log = $freshLog.FullName
        latest_log_write_time = $freshLog.LastWriteTime.ToString('o')
        validation = @($validation)
        protected_before = $BeforeListeners
        protected_after = $AfterListeners
    } | ConvertTo-Json -Depth 10
} catch {
    $failure = $_.Exception.Message
    try {
        Get-RealtimeShells | Stop-Process -Force -ErrorAction SilentlyContinue
        foreach ($key in $Destinations.Keys) {
            $before = Join-Path $BackupRoot "$key.before"
            if (Test-Path -LiteralPath $before -PathType Leaf) {
                Copy-Item -LiteralPath $before -Destination $Destinations[$key] -Force
            } else {
                Remove-Item -LiteralPath $Destinations[$key] -Force -ErrorAction SilentlyContinue
            }
        }
        Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
        Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
        $rollbackApplied = $true
    } catch {
        $failure = "$failure; rollback_failed=$($_.Exception.Message)"
    }
    [ordered]@{
        schema = 'ops.22012.realtime-sync-pwsh7-migration.result.v1'
        ok = $false
        error = $failure
        backup = $BackupRoot
        rollback_applied = $rollbackApplied
    } | ConvertTo-Json -Depth 6
    exit 2
}
