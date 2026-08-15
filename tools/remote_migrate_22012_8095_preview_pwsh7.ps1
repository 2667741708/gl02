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
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\OPS-22012-PWSH7-ALL-20260811\run_22012_8095_preview.ps1'
$Runner = Join-Path $Root 'tools\run_22012_8095_preview.ps1'
$TaskPath = '\BlastFurnaceServices\'
$TaskName = 'V3AutoPreviewProxy8095'
$ProtectedPorts = @(8093, 8094, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-8095" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

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
        if ((@($Before[$key]) -join ',') -cne (@($After[$key]) -join ',')) { throw "Protected listener changed: $port" }
    }
}

function Wait-Port([bool]$Listening, [int]$TimeoutSeconds = 180) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $found = @(Get-NetTCPConnection -State Listen -LocalPort 8095 -ErrorAction SilentlyContinue).Count -gt 0
        if ($found -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port 8095 did not reach listening=$Listening"
}

function Install-Atomically([string]$Source, [string]$Destination) {
    $temporary = "$Destination.$PID.pwsh7.tmp"
    $replaceBackup = "$Destination.$PID.pwsh7.replace.bak"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    try { [IO.File]::Replace($temporary, $Destination, $replaceBackup, $true) }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
    }
}

function Get-Task {
    return Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
}

function Get-WrapperProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        [string]$_.Name -in @('powershell.exe', 'pwsh.exe') -and [string]$_.CommandLine -like '*run_22012_8095_preview.ps1*'
    })
}

foreach ($required in @($Stage, $Runner, $PwshPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file missing: $required" }
}
$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($Stage, [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) { throw "Staged runner parse failed: $($errors[0].Message)" }

$BeforeListeners = Get-Listeners
Wait-Port $true 60
$Task = Get-Task
$Action = @($Task.Actions)[0]
if ([string]$Action.Arguments -notlike '*run_22012_8095_preview.ps1*') { throw '8095 task identity mismatch.' }
$TriggerEnabledBefore = @($Task.Triggers | Where-Object { [bool]$_.Enabled }).Count -gt 0
$TaskWasEnabled = [int]$Task.State -ne 1
$Wrappers = Get-WrapperProcesses
if ($Wrappers.Count -ne 1 -or [string]$Wrappers[0].Name -ine 'powershell.exe') { throw 'Expected one legacy 8095 wrapper.' }
$ListenerBefore = Get-NetTCPConnection -State Listen -LocalPort 8095 -ErrorAction Stop | Select-Object -First 1
$PythonBefore = Get-CimInstance Win32_Process -Filter "ProcessId=$($ListenerBefore.OwningProcess)" -ErrorAction Stop
if ([string]$PythonBefore.Name -ine 'python.exe' -or [string]$PythonBefore.CommandLine -notlike '*ollama_proxy_server_8095.py*') {
    throw '8095 listener identity mismatch.'
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$TaskXml = Export-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
[IO.File]::WriteAllText((Join-Path $BackupRoot 'task_before.xml'), $TaskXml, $Utf8NoBom)
Copy-Item -LiteralPath $Runner -Destination (Join-Path $BackupRoot 'runner_before.ps1') -Force

$rollbackApplied = $false
try {
    if ($TaskWasEnabled) {
        Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null
    }
    Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    Install-Atomically $Stage $Runner
    $validation = @(& $PwshPath -NoLogo -NoProfile -File $Runner -ValidateOnly 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "8095 ValidateOnly failed: $($validation -join ' ')" }
    $desiredArguments = ([string]$Action.Arguments) -replace '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
    $newAction = New-ScheduledTaskAction -Execute $PwshPath -Argument $desiredArguments
    Set-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $newAction | Out-Null

    Stop-Process -Id ([int]$Wrappers[0].ProcessId) -Force -ErrorAction SilentlyContinue
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $staleWrappers = @(Get-WrapperProcesses)
        foreach ($staleWrapper in $staleWrappers) {
            Stop-Process -Id ([int]$staleWrapper.ProcessId) -Force -ErrorAction SilentlyContinue
        }
        $staleChildren = @(Get-CimInstance Win32_Process | Where-Object {
            [string]$_.Name -ieq 'python.exe' -and [string]$_.CommandLine -like '*ollama_proxy_server_8095.py*'
        })
        foreach ($staleChild in $staleChildren) {
            Stop-Process -Id ([int]$staleChild.ProcessId) -Force -ErrorAction SilentlyContinue
        }
        if (-not (Get-NetTCPConnection -State Listen -LocalPort 8095 -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    Wait-Port $false 60
    if ($TaskWasEnabled) { Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null }
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    Wait-Port $true 180
    Start-Sleep -Seconds 2
    $Response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8095/?cb=pwsh7-migration' -TimeoutSec 30
    if ([int]$Response.StatusCode -ne 200) { throw "8095 HTTP status is $($Response.StatusCode)" }
    $WrappersAfter = Get-WrapperProcesses
    if ($WrappersAfter.Count -ne 1 -or [string]$WrappersAfter[0].Name -ine 'pwsh.exe') { throw '8095 PowerShell 7 wrapper verification failed.' }
    $TaskAfter = Get-Task
    if ([string](@($TaskAfter.Actions)[0].Execute) -ine $PwshPath) { throw '8095 task action verification failed.' }
    $TriggerEnabledAfter = @($TaskAfter.Triggers | Where-Object { [bool]$_.Enabled }).Count -gt 0
    if ($TriggerEnabledAfter -ne $TriggerEnabledBefore) { throw '8095 trigger state changed.' }
    $AfterListeners = Get-Listeners
    Assert-ListenersUnchanged $BeforeListeners $AfterListeners
    $ListenerAfter = Get-NetTCPConnection -State Listen -LocalPort 8095 -ErrorAction Stop | Select-Object -First 1

    [ordered]@{
        schema = 'ops.22012.8095-preview-pwsh7-migration.result.v1'
        ok = $true
        backup = $BackupRoot
        rollback_applied = $false
        old_wrapper_pid = [int]$Wrappers[0].ProcessId
        new_wrapper_pid = [int]$WrappersAfter[0].ProcessId
        old_listener_pid = [int]$ListenerBefore.OwningProcess
        new_listener_pid = [int]$ListenerAfter.OwningProcess
        task_execute = [string](@($TaskAfter.Actions)[0].Execute)
        trigger_enabled_preserved = $true
        http_status = [int]$Response.StatusCode
        validation = @($validation)
        protected_before = $BeforeListeners
        protected_after = $AfterListeners
    } | ConvertTo-Json -Depth 10
} catch {
    $failure = $_.Exception.Message
    try {
        Get-WrapperProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath (Join-Path $BackupRoot 'runner_before.ps1') -Destination $Runner -Force
        Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml $TaskXml -Force | Out-Null
        Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
        Wait-Port $true 180
        $rollbackApplied = $true
    } catch {
        $failure = "$failure; rollback_failed=$($_.Exception.Message)"
    }
    [ordered]@{
        schema = 'ops.22012.8095-preview-pwsh7-migration.result.v1'
        ok = $false
        error = $failure
        backup = $BackupRoot
        rollback_applied = $rollbackApplied
    } | ConvertTo-Json -Depth 6
    exit 2
}
