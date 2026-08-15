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
$ProgressPreference = 'SilentlyContinue'

$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-services" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))
$ProtectedPorts = @(8093, 8094, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)
$GenericRunner = Join-Path $Root 'tools\run_managed_nssm_process.ps1'
$GenericHealth = Join-Path $Root 'tools\check_managed_nssm_service_health.ps1'
$Targets = @(
    [ordered]@{
        service = 'BFV4PreviewWs8768'
        port = 8768
        runner = Join-Path $Root 'tools\run_v4_8768_ws_service.ps1'
        runner_validate_args = @()
        health_task = 'BFV4PreviewWs8768HealthCheck'
        health_runner = Join-Path $Root 'tools\check_v4_8768_service_health.ps1'
        health_validate_args = @()
    },
    [ordered]@{
        service = 'BFOllama11434'
        port = 11434
        runner = $GenericRunner
        runner_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFOllama11434.json'), '-ValidateOnly')
        health_task = 'BFOllama11434HealthCheck'
        health_runner = $GenericHealth
        health_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFOllama11434.json'), '-ValidateOnly')
    },
    [ordered]@{
        service = 'BFChronos8777'
        port = 8777
        runner = $GenericRunner
        runner_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFChronos8777.json'), '-ValidateOnly')
        health_task = 'BFChronos8777HealthCheck'
        health_runner = $GenericHealth
        health_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFChronos8777.json'), '-ValidateOnly')
    },
    [ordered]@{
        service = 'BFV3AutoPreviewWs8767'
        port = 8767
        runner = $GenericRunner
        runner_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFV3AutoPreviewWs8767.json'), '-ValidateOnly')
        health_task = 'BFV3AutoPreviewWs8767HealthCheck'
        health_runner = $GenericHealth
        health_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFV3AutoPreviewWs8767.json'), '-ValidateOnly')
    },
    [ordered]@{
        service = 'BFBaselineProxy8096'
        port = 8096
        runner = $GenericRunner
        runner_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFBaselineProxy8096.json'), '-ValidateOnly')
        health_task = 'BFBaselineProxy8096HealthCheck'
        health_runner = $GenericHealth
        health_validate_args = @('-ConfigPath', (Join-Path $Root 'tools\service_configs\22012_BFBaselineProxy8096.json'), '-ValidateOnly')
    }
)

function Get-StateName($Task) {
    switch ([int]$Task.State) {
        1 { return 'Disabled' }
        2 { return 'Queued' }
        3 { return 'Ready' }
        4 { return 'Running' }
        default { return "Unknown:$([int]$Task.State)" }
    }
}

function Get-HealthTask($Target) {
    $matches = @(Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $Target.health_task -ErrorAction SilentlyContinue)
    if ($matches.Count -ne 1) { throw "Health task identity mismatch: $($Target.health_task)" }
    return $matches[0]
}

function Wait-TaskIdle($Target, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-StateName (Get-HealthTask $Target)) -ne 'Running') { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Health task did not become idle: $($Target.health_task)"
}

function Wait-ServiceState([string]$Name, [string]$Expected, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Expected) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Service $Name did not reach $Expected"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 180) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $found = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue).Count -gt 0
        if ($found -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Get-ListenerSnapshot {
    $snapshot = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $pids = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object)
        if ($pids.Count -eq 0) { throw "Protected listener is missing: $port" }
        $snapshot[[string]$port] = @($pids | ForEach-Object { [int]$_ })
    }
    return $snapshot
}

function Assert-Isolation($Before, $After, [int]$ChangedPort) {
    foreach ($port in $ProtectedPorts) {
        $key = [string]$port
        if ($port -eq $ChangedPort) {
            if (@($After[$key]).Count -eq 0) { throw "Target port was not restored: $port" }
            continue
        }
        if ((@($Before[$key]) -join ',') -cne (@($After[$key]) -join ',')) {
            throw "Protected listener changed unexpectedly: $port"
        }
    }
}

function Assert-Syntax([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Runtime file missing: $Path" }
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "PowerShell parse failed for ${Path}: $($errors[0].Message)" }
}

function Invoke-Validate([string]$Path, [object[]]$Arguments) {
    if (@($Arguments).Count -eq 0) { return @('syntax_only=true') }
    $output = @(& $PwshPath -NoLogo -NoProfile -File $Path @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "ValidateOnly failed for ${Path}: $($output -join ' ')" }
    return @($output)
}

function Get-RegistryRecord([string]$ServiceName) {
    $path = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
    $record = Get-ItemProperty -LiteralPath $path -ErrorAction Stop
    return [ordered]@{
        path = $path
        application = [string]$record.Application
        app_parameters = [string]$record.AppParameters
        app_directory = [string]$record.AppDirectory
    }
}

function Test-PwshDescendant([string]$ServiceName, [string]$RunnerMarker) {
    $service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction Stop
    $processes = @(Get-CimInstance Win32_Process)
    $queue = [Collections.Generic.Queue[int]]::new()
    $visited = [Collections.Generic.HashSet[int]]::new()
    $queue.Enqueue([int]$service.ProcessId)
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        if (-not $visited.Add($parent)) { continue }
        foreach ($child in @($processes | Where-Object { [int]$_.ParentProcessId -eq $parent })) {
            if ([string]$child.Name -ieq 'pwsh.exe' -and [string]$child.CommandLine -like "*$RunnerMarker*") { return $true }
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    return $false
}

function Wait-HealthResult($Target, [datetime]$StartedAfter, [int]$TimeoutSeconds = 120) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-HealthTask $Target
        $info = Get-ScheduledTaskInfo -TaskPath '\BlastFurnaceServices\' -TaskName $Target.health_task
        if ((Get-StateName $task) -ne 'Running' -and $info.LastRunTime -ge $StartedAfter) {
            if ([long]$info.LastTaskResult -ne 0) { throw "Health task failed: $($Target.health_task) result=$($info.LastTaskResult)" }
            return $info
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Health task validation timed out: $($Target.health_task)"
}

function New-PreservedTaskAction([string]$Arguments, [string]$WorkingDirectory) {
    if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
        return New-ScheduledTaskAction -Execute $PwshPath -Argument $Arguments
    }
    return New-ScheduledTaskAction -Execute $PwshPath -Argument $Arguments -WorkingDirectory $WorkingDirectory
}

if (-not (Test-Path -LiteralPath $PwshPath -PathType Leaf)) { throw 'PowerShell 7.6.4 is unavailable.' }
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$LockTaken = $false
$Results = [Collections.Generic.List[object]]::new()

try {
    try { $LockTaken = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $LockTaken = $true }
    if (-not $LockTaken) { throw 'Another guarded deployment owns the production mutex.' }

    foreach ($target in $Targets) {
        Assert-Syntax $target.runner
        Assert-Syntax $target.health_runner
        $runnerValidation = Invoke-Validate $target.runner $target.runner_validate_args
        $healthValidation = Invoke-Validate $target.health_runner $target.health_validate_args

        $beforeListeners = Get-ListenerSnapshot
        $serviceBefore = Get-Service -Name $target.service -ErrorAction Stop
        if ($serviceBefore.Status -ne 'Running') { throw "Service is not running before migration: $($target.service)" }
        $registryBefore = Get-RegistryRecord $target.service
        if ([IO.Path]::GetFileName($registryBefore.application.Trim('"')) -inotmatch '^(?:powershell|pwsh)\.exe$') {
            throw "Unexpected NSSM runtime: $($target.service)"
        }
        if ($registryBefore.app_parameters -notlike "*$($target.runner)*") { throw "Service runner mismatch: $($target.service)" }

        $healthTask = Get-HealthTask $target
        $healthStateBefore = Get-StateName $healthTask
        $healthWasEnabled = $healthStateBefore -ne 'Disabled'
        $healthActionBefore = @($healthTask.Actions)[0]
        if ([string]$healthActionBefore.Arguments -notlike "*$($target.health_runner)*") {
            throw "Health runner mismatch: $($target.health_task)"
        }

        $targetBackup = Join-Path $BackupRoot $target.service
        New-Item -ItemType Directory -Path $targetBackup -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $targetBackup 'health_task_before.xml'), (Export-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task), $Utf8NoBom)
        [IO.File]::WriteAllText((Join-Path $targetBackup 'service_registry_before.json'), ($registryBefore | ConvertTo-Json -Depth 5), $Utf8NoBom)

        $rollbackApplied = $false
        try {
            if ($healthWasEnabled) {
                Disable-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task | Out-Null
                Wait-TaskIdle $target
            }

            $alreadyPwsh = [string]$registryBefore.application -ieq $PwshPath
            if (-not $alreadyPwsh) {
                Stop-Service -Name $target.service -Force -ErrorAction Stop
                Wait-ServiceState $target.service 'Stopped'
                Wait-Port $target.port $false
                Set-ItemProperty -LiteralPath $registryBefore.path -Name Application -Value $PwshPath -Type String
                Start-Service -Name $target.service -ErrorAction Stop
                Wait-ServiceState $target.service 'Running'
                Wait-Port $target.port $true
            }

            $desiredHealthArguments = ([string]$healthActionBefore.Arguments) -replace '(?i)^\s*-NoProfile\s+-ExecutionPolicy\s+Bypass\s+', '-NoLogo -NoProfile '
            $newHealthAction = New-PreservedTaskAction $desiredHealthArguments ([string]$healthActionBefore.WorkingDirectory)
            Set-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task -Action $newHealthAction | Out-Null
            if ($healthWasEnabled) { Enable-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task | Out-Null }

            if (-not (Test-PwshDescendant $target.service ([IO.Path]::GetFileName($target.runner)))) {
                throw "No PowerShell 7 runner descendant found for $($target.service)"
            }
            $healthStarted = Get-Date
            Start-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task
            $healthInfo = Wait-HealthResult $target $healthStarted
            $afterListeners = Get-ListenerSnapshot
            Assert-Isolation $beforeListeners $afterListeners $target.port
            $registryAfter = Get-RegistryRecord $target.service
            if ([string]$registryAfter.application -ine $PwshPath) { throw "Service runtime verification failed: $($target.service)" }
            $healthAfter = Get-HealthTask $target
            if ([string](@($healthAfter.Actions)[0].Execute) -ine $PwshPath) { throw "Health runtime verification failed: $($target.health_task)" }

            $Results.Add([ordered]@{
                service = $target.service
                port = $target.port
                changed = -not $alreadyPwsh
                service_application_before = $registryBefore.application
                service_application_after = $registryAfter.application
                health_task = $target.health_task
                health_result = [long]$healthInfo.LastTaskResult
                runner_validation = @($runnerValidation)
                health_validation = @($healthValidation)
                backup = $targetBackup
                rollback_applied = $false
                protected_before = $beforeListeners
                protected_after = $afterListeners
            })
        } catch {
            $failure = $_.Exception.Message
            try {
                Stop-Service -Name $target.service -Force -ErrorAction SilentlyContinue
                Wait-ServiceState $target.service 'Stopped'
                Set-ItemProperty -LiteralPath $registryBefore.path -Name Application -Value $registryBefore.application -Type String
                Start-Service -Name $target.service -ErrorAction Stop
                Wait-ServiceState $target.service 'Running'
                Wait-Port $target.port $true
                Register-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task -Xml (Export-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task) -Force | Out-Null
                $xml = [IO.File]::ReadAllText((Join-Path $targetBackup 'health_task_before.xml'), [Text.Encoding]::UTF8)
                Register-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName $target.health_task -Xml $xml -Force | Out-Null
                $rollbackApplied = $true
            } catch {
                $failure = "$failure; rollback_failed=$($_.Exception.Message)"
            }
            [ordered]@{
                schema = 'ops.22012.active-services-pwsh7-migration.result.v1'
                ok = $false
                failed_target = $target.service
                error = $failure
                rollback_applied = $rollbackApplied
                backup_root = $BackupRoot
                completed = @($Results)
            } | ConvertTo-Json -Depth 12
            exit 2
        }
    }

    [ordered]@{
        schema = 'ops.22012.active-services-pwsh7-migration.result.v1'
        ok = $true
        powershell_version = $PSVersionTable.PSVersion.ToString()
        backup_root = $BackupRoot
        results = @($Results)
    } | ConvertTo-Json -Depth 12
} finally {
    if ($LockTaken) { try { $Mutex.ReleaseMutex() } catch { } }
    $Mutex.Dispose()
}
