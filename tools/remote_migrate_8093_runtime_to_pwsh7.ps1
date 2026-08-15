[CmdletBinding()]
param(
    [ValidateSet('Audit', 'Apply', 'Rollback')]
    [string]$Mode = 'Audit',
    [string]$Target = '',
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\OPS-8093-PWSH7-RUNTIME-MIGRATION-20260811',
    [string]$ExpectedTargetSha256 = '',
    [string]$ExpectedStagedSha256 = '',
    [string]$BackupPath = '',
    [string]$OperationPlan = '',
    [string]$NssmPath = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\nssm\nssm-2.24\win64\nssm.exe'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This migration requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ProgressPreference = 'SilentlyContinue'

$RequirementId = 'OPS-8093-PWSH7-RUNTIME-MIGRATION-20260811'
$ServiceName = 'BFV4PreviewProxy8093'
$NssmRegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$RunnerPath = Join-Path $Root 'tools\run_managed_nssm_process.ps1'
$HealthPath = Join-Path $Root 'tools\check_managed_nssm_service_health.ps1'
$BaselinePath = Join-Path $Root 'tools\run_v4_daily_baseline.ps1'
$ManagerPath = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ProtectedPorts = @(8093, 8768, 8094, 8770, 5432, 8892, 11434)
$Mutex = $null
$LockTaken = $false

if ([string]::IsNullOrWhiteSpace($OperationPlan)) {
    $OperationPlan = Join-Path $StageRoot 'operation.json'
}
if (Test-Path -LiteralPath $OperationPlan -PathType Leaf) {
    $plan = [IO.File]::ReadAllText($OperationPlan, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ([string]$plan.schema -ne 'ops.8093.pwsh7-runtime-migration.operation.v1' -or
        [string]$plan.requirement_id -ne $RequirementId) {
        throw 'Migration operation plan identity mismatch.'
    }
    if (-not $PSBoundParameters.ContainsKey('Mode')) { $Mode = [string]$plan.mode }
    if (-not $PSBoundParameters.ContainsKey('Target')) { $Target = [string]$plan.target }
    if (-not $PSBoundParameters.ContainsKey('ExpectedTargetSha256')) { $ExpectedTargetSha256 = [string]$plan.expected_target_sha256 }
    if (-not $PSBoundParameters.ContainsKey('ExpectedStagedSha256')) { $ExpectedStagedSha256 = [string]$plan.expected_staged_sha256 }
    if (-not $PSBoundParameters.ContainsKey('BackupPath')) { $BackupPath = [string]$plan.backup_path }
}
$AllowedModes = @('Audit', 'Apply', 'Rollback')
$AllowedTargets = @('ServiceWrapper', 'HealthTask', 'DailyBaselineTask', 'LegacyV3Proxy8093', 'LegacyNewProject8093')
if ($AllowedModes -notcontains $Mode) { throw "Unsupported migration mode: $Mode" }
if ($AllowedTargets -notcontains $Target) { throw "Unsupported migration target: $Target" }

function Get-TargetSpec([string]$Name) {
    switch ($Name) {
        'ServiceWrapper' {
            return [ordered]@{
                kind = 'service'
                task_path = $null
                task_name = $null
                action_marker = $null
                staged = Join-Path $StageRoot 'run_managed_nssm_process.ps1'
                destination = $RunnerPath
            }
        }
        'HealthTask' {
            return [ordered]@{
                kind = 'active_task'
                task_path = '\BlastFurnaceServices\'
                task_name = 'BFV4PreviewProxy8093HealthCheck'
                action_marker = 'check_managed_nssm_service_health.ps1'
                staged = Join-Path $StageRoot 'check_managed_nssm_service_health.ps1'
                destination = $HealthPath
            }
        }
        'DailyBaselineTask' {
            return [ordered]@{
                kind = 'active_task'
                task_path = '\'
                task_name = 'BlastFurnace8093DailyBaseline20d'
                action_marker = 'run_v4_daily_baseline.ps1'
                staged = Join-Path $StageRoot 'run_v4_daily_baseline.ps1'
                destination = $BaselinePath
            }
        }
        'LegacyV3Proxy8093' {
            return [ordered]@{
                kind = 'legacy_task'
                task_path = '\'
                task_name = 'BlastFurnaceV3Proxy8093'
                action_marker = 'run_proxy_8093.ps1'
                staged = $null
                destination = $null
            }
        }
        'LegacyNewProject8093' {
            return [ordered]@{
                kind = 'legacy_task'
                task_path = '\'
                task_name = 'BlastFurnace8093Proxy_NewProject'
                action_marker = 'run_proxy_8093_db.ps1'
                staged = $null
                destination = $null
            }
        }
    }
}

function Get-ExactTask([string]$TaskPath, [string]$TaskName) {
    $all = @(Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
    $exact = @($all | Where-Object { $_.TaskPath -eq $TaskPath })
    if ($exact.Count -ne 1) {
        $paths = @($all | ForEach-Object { $_.TaskPath }) -join ','
        throw "Task identity mismatch for $TaskPath$TaskName; discovered_paths=$paths"
    }
    return $exact[0]
}

function Get-TaskStateName($Task) {
    switch ([int]$Task.State) {
        1 { return 'Disabled' }
        2 { return 'Queued' }
        3 { return 'Ready' }
        4 { return 'Running' }
        default { return "Unknown:$([int]$Task.State)" }
    }
}

function Assert-TaskIdentity($Spec, $Task) {
    $actions = @($Task.Actions)
    if ($actions.Count -ne 1) {
        throw "Task $($Spec.task_path)$($Spec.task_name) must have exactly one action."
    }
    $action = $actions[0]
    $text = "$($action.Execute) $($action.Arguments) $($action.WorkingDirectory)"
    if ($text -notlike "*$($Spec.action_marker)*") {
        throw "Task action marker mismatch for $($Spec.task_path)$($Spec.task_name)."
    }
    if ($Spec.kind -eq 'legacy_task') {
        if ([IO.Path]::GetFileName([string]$action.Execute) -ine 'powershell.exe') {
            throw "Legacy task executable changed for $($Spec.task_path)$($Spec.task_name)."
        }
        $StateName = Get-TaskStateName $Task
        if ($StateName -notin @('Ready', 'Disabled')) {
            throw "Legacy task has unexpected state $StateName."
        }
    }
}

function Wait-TaskIdle([string]$TaskPath, [string]$TaskName, [int]$TimeoutSeconds = 45) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $task = Get-ExactTask $TaskPath $TaskName
        if ((Get-TaskStateName $task) -ne 'Running') { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Task $TaskPath$TaskName did not become idle within $TimeoutSeconds seconds."
}

function Get-ListenerSnapshot {
    $snapshot = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $pids = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            Sort-Object)
        if ($pids.Count -eq 0) { throw "Protected listener is missing: $port" }
        $snapshot[[string]$port] = @($pids | ForEach-Object { [int]$_ })
    }
    return $snapshot
}

function Assert-ListenerIsolation($Before, $After, [bool]$Allow8093PidChange) {
    foreach ($port in $ProtectedPorts) {
        $key = [string]$port
        if ($port -eq 8093 -and $Allow8093PidChange) {
            if (@($After[$key]).Count -eq 0) { throw '8093 listener was not restored.' }
            continue
        }
        $beforeText = (@($Before[$key]) -join ',')
        $afterText = (@($After[$key]) -join ',')
        if ($beforeText -cne $afterText) {
            throw "Protected listener PID changed for port $port; before=$beforeText after=$afterText"
        }
    }
}

function Assert-8093Healthy {
    $service = Get-Service -Name $ServiceName -ErrorAction Stop
    if ($service.Status -ne 'Running') { throw "$ServiceName is not Running." }
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue)
    if ($listener.Count -eq 0) { throw 'Port 8093 is not listening.' }
    $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:8093/?cb=pwsh7-migration-{0}" -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) -TimeoutSec 20
    if ([int]$response.StatusCode -ne 200) { throw "8093 HTTP status is $($response.StatusCode)." }
}

function Get-NssmValue([string]$Setting) {
    if ($Setting -notin @('Application', 'AppParameters', 'AppDirectory')) {
        throw "Unsupported NSSM registry setting: $Setting"
    }
    $record = Get-ItemProperty -LiteralPath $NssmRegistryPath -Name $Setting -ErrorAction Stop
    return ([string]$record.$Setting).Trim()
}

function Set-NssmValue([string]$Setting, [string]$Value) {
    $output = @(& $NssmPath set $ServiceName $Setting $Value 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM set failed for $Setting with exit code $LASTEXITCODE output=$($output -join ' ')"
    }
}

function Assert-ServiceWrapperIdentity($ServiceRecord) {
    $applicationName = [IO.Path]::GetFileName(([string]$ServiceRecord.application).Trim('"'))
    if ($applicationName -inotmatch '^(powershell|pwsh)\.exe$') {
        throw "Unexpected NSSM application for ${ServiceName}: $($ServiceRecord.application)"
    }
    if ([string]$ServiceRecord.app_parameters -notlike '*run_managed_nssm_process.ps1*' -or
        [string]$ServiceRecord.app_parameters -notlike '*22012_BFV4PreviewProxy8093.json*') {
        throw "Unexpected NSSM AppParameters for $ServiceName."
    }
}

function Invoke-ManagedServiceAction([ValidateSet('stop', 'start')] [string]$Action) {
    $output = @(& $PwshPath -NoLogo -NoProfile -File $ManagerPath -Action $Action -ConfigPath $ConfigPath 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Managed service action $Action failed with exit code $LASTEXITCODE output=$($output -join ' ')"
    }
}

function Wait-ServiceState([string]$Expected, [int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $state = (Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString()
        if ($state -eq $Expected) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$ServiceName did not reach $Expected within $TimeoutSeconds seconds."
}

function Wait-Port([bool]$ShouldListen, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $listening = @(Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue).Count -gt 0
        if ($listening -eq $ShouldListen) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port 8093 did not reach listening=$ShouldListen within $TimeoutSeconds seconds."
}

function Test-PwshServiceDescendant {
    $service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction Stop
    $queue = [System.Collections.Generic.Queue[int]]::new()
    $queue.Enqueue([int]$service.ProcessId)
    $visited = [System.Collections.Generic.HashSet[int]]::new()
    $processes = @(Get-CimInstance Win32_Process)
    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        if (-not $visited.Add($parent)) { continue }
        foreach ($child in @($processes | Where-Object { [int]$_.ParentProcessId -eq $parent })) {
            if ([string]$child.Name -ieq 'pwsh.exe' -and [string]$child.CommandLine -like '*run_managed_nssm_process.ps1*') {
                return $true
            }
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    return $false
}

function Install-FileAtomically([string]$Source, [string]$Destination) {
    $temporary = "$Destination.$PID.migrate.tmp"
    $replaceBackup = "$Destination.$PID.replace.bak"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    try {
        if (Test-Path -LiteralPath $Destination -PathType Leaf) {
            [IO.File]::Replace($temporary, $Destination, $replaceBackup, $true)
        } else {
            [IO.File]::Move($temporary, $Destination)
        }
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction SilentlyContinue
    }
}

function Assert-StagedFile($Spec) {
    if ([string]::IsNullOrWhiteSpace($ExpectedTargetSha256) -or [string]::IsNullOrWhiteSpace($ExpectedStagedSha256)) {
        throw 'ExpectedTargetSha256 and ExpectedStagedSha256 are mandatory for runtime-file migration.'
    }
    if (-not (Test-Path -LiteralPath $Spec.destination -PathType Leaf)) {
        throw "Runtime target missing: $($Spec.destination)"
    }
    if (-not (Test-Path -LiteralPath $Spec.staged -PathType Leaf)) {
        throw "Staged runtime file missing: $($Spec.staged)"
    }
    $targetHash = (Get-FileHash -LiteralPath $Spec.destination -Algorithm SHA256).Hash
    $stageHash = (Get-FileHash -LiteralPath $Spec.staged -Algorithm SHA256).Hash
    if ($targetHash -ine $ExpectedTargetSha256) {
        throw "Runtime target baseline changed: $targetHash"
    }
    if ($stageHash -ine $ExpectedStagedSha256) {
        throw "Staged runtime hash changed: $stageHash"
    }
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Spec.staged, [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw "Staged PowerShell syntax failed: $($errors[0].Message)" }
    return [ordered]@{ target = $targetHash; staged = $stageHash }
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function New-Backup($Spec, $BeforeListeners) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $directory = Join-Path $Root "logs\deploy_backups\8093_pwsh7_runtime\$stamp-$Target"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $manifest = [ordered]@{
        schema = 'ops.8093.pwsh7-runtime-migration.backup.v1'
        requirement_id = $RequirementId
        target = $Target
        created_at = [DateTimeOffset]::Now.ToString('o')
        root = $Root
        runtime_backup = $null
        task_xml = $null
        health_task_xml = $null
        nssm = $null
        protected_before = $BeforeListeners
    }
    if ($Spec.destination) {
        $runtimeBackup = Join-Path $directory ([IO.Path]::GetFileName([string]$Spec.destination))
        Copy-Item -LiteralPath $Spec.destination -Destination $runtimeBackup -Force
        $manifest.runtime_backup = $runtimeBackup
    }
    if ($Spec.task_name) {
        $task = Get-ExactTask $Spec.task_path $Spec.task_name
        Assert-TaskIdentity $Spec $task
        $taskXmlPath = Join-Path $directory 'task_before.xml'
        Write-Utf8NoBom $taskXmlPath (Export-ScheduledTask -TaskPath $Spec.task_path -TaskName $Spec.task_name)
        $manifest.task_xml = $taskXmlPath
    }
    if ($Spec.kind -eq 'service') {
        $healthXmlPath = Join-Path $directory 'health_task_before.xml'
        Write-Utf8NoBom $healthXmlPath (Export-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFV4PreviewProxy8093HealthCheck')
        $manifest.health_task_xml = $healthXmlPath
        $manifest.nssm = [ordered]@{
            application = Get-NssmValue 'Application'
            app_parameters = Get-NssmValue 'AppParameters'
            app_directory = Get-NssmValue 'AppDirectory'
        }
        @(& sc.exe qc $ServiceName 2>&1) | Set-Content -LiteralPath (Join-Path $directory 'service_qc_before.txt') -Encoding utf8
    }
    $manifestPath = Join-Path $directory 'manifest.json'
    Write-Utf8NoBom $manifestPath ($manifest | ConvertTo-Json -Depth 10)
    return [pscustomobject]@{ directory = $directory; manifest_path = $manifestPath; manifest = $manifest }
}

function Restore-TaskXml([string]$TaskPath, [string]$TaskName, [string]$XmlPath) {
    $xml = [IO.File]::ReadAllText($XmlPath, [Text.Encoding]::UTF8)
    Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml $xml -Force | Out-Null
}

function Restore-FromManifest($Manifest) {
    $restoreSpec = Get-TargetSpec ([string]$Manifest.target)
    if ($Manifest.runtime_backup) {
        Install-FileAtomically -Source ([string]$Manifest.runtime_backup) -Destination ([string]$restoreSpec.destination)
    }
    if ($restoreSpec.kind -eq 'service') {
        $healthTask = Get-ExactTask '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck'
        if ((Get-TaskStateName $healthTask) -ne 'Disabled') {
            Disable-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFV4PreviewProxy8093HealthCheck' | Out-Null
            Wait-TaskIdle '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck' 60
        }
        $service = Get-Service -Name $ServiceName -ErrorAction Stop
        if ($service.Status -ne 'Stopped') {
            Invoke-ManagedServiceAction 'stop'
            Wait-ServiceState 'Stopped'
            Wait-Port $false
        }
        Set-NssmValue 'Application' ([string]$Manifest.nssm.application)
        Set-NssmValue 'AppParameters' ([string]$Manifest.nssm.app_parameters)
        Set-NssmValue 'AppDirectory' ([string]$Manifest.nssm.app_directory)
        Invoke-ManagedServiceAction 'start'
        Wait-ServiceState 'Running'
        Wait-Port $true
        Assert-8093Healthy
        if ($Manifest.health_task_xml) {
            Restore-TaskXml '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck' ([string]$Manifest.health_task_xml)
        }
    } elseif ($Manifest.task_xml) {
        Restore-TaskXml $restoreSpec.task_path $restoreSpec.task_name ([string]$Manifest.task_xml)
    }
}

function Get-AuditRecord($Spec) {
    $record = [ordered]@{
        target = $Target
        kind = $Spec.kind
        runtime = $null
        task = $null
        service = $null
    }
    if ($Spec.destination) {
        $record.runtime = [ordered]@{
            path = $Spec.destination
            exists = Test-Path -LiteralPath $Spec.destination -PathType Leaf
            sha256 = if (Test-Path -LiteralPath $Spec.destination -PathType Leaf) { (Get-FileHash -LiteralPath $Spec.destination -Algorithm SHA256).Hash } else { $null }
        }
    }
    if ($Spec.task_name) {
        $task = Get-ExactTask $Spec.task_path $Spec.task_name
        Assert-TaskIdentity $Spec $task
        $record.task = [ordered]@{
            path = $task.TaskPath
            name = $task.TaskName
            state = Get-TaskStateName $task
            actions = @($task.Actions | Select-Object Execute, Arguments, WorkingDirectory)
        }
    }
    if ($Spec.kind -eq 'service') {
        $record.service = [ordered]@{
            state = (Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString()
            application = Get-NssmValue 'Application'
            app_parameters = Get-NssmValue 'AppParameters'
            app_directory = Get-NssmValue 'AppDirectory'
        }
        Assert-ServiceWrapperIdentity $record.service
    }
    return $record
}

$Spec = Get-TargetSpec $Target
foreach ($required in @($PwshPath, $ConfigPath, $ManagerPath, $NssmPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file missing: $required" }
}
$config = [IO.File]::ReadAllText($ConfigPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
if ([string]$config.serviceName -ne $ServiceName) { throw '8093 service config identity mismatch.' }

if ($Mode -eq 'Audit') {
    $listeners = Get-ListenerSnapshot
    Assert-8093Healthy
    [ordered]@{
        schema = 'ops.8093.pwsh7-runtime-migration.audit.v1'
        requirement_id = $RequirementId
        ok = $true
        read_only = $true
        audit = Get-AuditRecord $Spec
        listeners = $listeners
    } | ConvertTo-Json -Depth 12
    exit 0
}

try {
    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) { throw 'Another 8093 deployment or recovery owns the global mutex.' }

    $BeforeListeners = Get-ListenerSnapshot
    Assert-8093Healthy

    if ($Mode -eq 'Rollback') {
        if ([string]::IsNullOrWhiteSpace($BackupPath)) { throw 'BackupPath is required for rollback.' }
        $manifestPath = Join-Path $BackupPath 'manifest.json'
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Backup manifest missing: $manifestPath" }
        $manifest = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
        if ([string]$manifest.requirement_id -ne $RequirementId -or [string]$manifest.target -ne $Target) {
            throw 'Rollback manifest identity mismatch.'
        }
        Restore-FromManifest $manifest
        $after = Get-ListenerSnapshot
        Assert-ListenerIsolation $BeforeListeners $after ($Target -eq 'ServiceWrapper')
        [ordered]@{
            schema = 'ops.8093.pwsh7-runtime-migration.result.v1'
            requirement_id = $RequirementId
            ok = $true
            mode = $Mode
            target = $Target
            rollback_applied = $true
            backup = $BackupPath
            protected_before = $BeforeListeners
            protected_after = $after
        } | ConvertTo-Json -Depth 10
        exit 0
    }

    $fileHashes = $null
    if ($Spec.destination) {
        $fileHashes = Assert-StagedFile $Spec
    }
    $auditBefore = Get-AuditRecord $Spec

    $desiredApplication = $PwshPath
    $desiredServiceArguments = "-NoLogo -NoProfile -File `"$RunnerPath`" -ConfigPath `"$ConfigPath`""
    $desiredTaskArguments = if ($Target -eq 'HealthTask') {
        "-NoLogo -NoProfile -File `"$HealthPath`" -ConfigPath `"$ConfigPath`""
    } elseif ($Target -eq 'DailyBaselineTask') {
        "-NoLogo -NoProfile -File `"$BaselinePath`""
    } else { $null }

    $alreadyDesired = $false
    if ($Target -eq 'ServiceWrapper') {
        $alreadyDesired = (
            $fileHashes.target -ieq $fileHashes.staged -and
            [string]$auditBefore.service.application -ieq $desiredApplication -and
            [string]$auditBefore.service.app_parameters -ceq $desiredServiceArguments
        )
    } elseif ($Spec.kind -eq 'active_task') {
        $action = @($auditBefore.task.actions)[0]
        $alreadyDesired = (
            $fileHashes.target -ieq $fileHashes.staged -and
            [string]$action.Execute -ieq $PwshPath -and
            [string]$action.Arguments -ceq $desiredTaskArguments
        )
    } elseif ($Spec.kind -eq 'legacy_task') {
        $alreadyDesired = [string]$auditBefore.task.state -eq 'Disabled'
    }

    if ($alreadyDesired) {
        $after = Get-ListenerSnapshot
        Assert-ListenerIsolation $BeforeListeners $after $false
        [ordered]@{
            schema = 'ops.8093.pwsh7-runtime-migration.result.v1'
            requirement_id = $RequirementId
            ok = $true
            mode = $Mode
            target = $Target
            changed = $false
            verified_noop = $true
            rollback_applied = $false
            protected_before = $BeforeListeners
            protected_after = $after
        } | ConvertTo-Json -Depth 10
        exit 0
    }

    $backup = New-Backup $Spec $BeforeListeners
    $rollbackApplied = $false
    $healthTaskWasEnabled = $false
    try {
        if ($Target -eq 'ServiceWrapper') {
            $healthTask = Get-ExactTask '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck'
            $healthTaskWasEnabled = (Get-TaskStateName $healthTask) -ne 'Disabled'
            if ($healthTaskWasEnabled) {
                Disable-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFV4PreviewProxy8093HealthCheck' | Out-Null
                Wait-TaskIdle '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck' 60
            }
            $validation = @(& $PwshPath -NoLogo -NoProfile -File $Spec.staged -ConfigPath $ConfigPath -ValidateOnly 2>&1)
            if ($LASTEXITCODE -ne 0) { throw "Staged service runner validation failed: $($validation -join ' ')" }
            Invoke-ManagedServiceAction 'stop'
            Wait-ServiceState 'Stopped'
            Wait-Port $false
            Install-FileAtomically -Source $Spec.staged -Destination $Spec.destination
            Set-NssmValue 'Application' $desiredApplication
            Set-NssmValue 'AppParameters' $desiredServiceArguments
            Set-NssmValue 'AppDirectory' $Root
            Invoke-ManagedServiceAction 'start'
            Wait-ServiceState 'Running'
            Wait-Port $true
            Assert-8093Healthy
            if (-not (Test-PwshServiceDescendant)) { throw 'No pwsh.exe service descendant owns the managed runner.' }
        } elseif ($Spec.kind -eq 'active_task') {
            $task = Get-ExactTask $Spec.task_path $Spec.task_name
            $taskWasEnabled = (Get-TaskStateName $task) -ne 'Disabled'
            if ($taskWasEnabled) {
                Disable-ScheduledTask -TaskPath $Spec.task_path -TaskName $Spec.task_name | Out-Null
                Wait-TaskIdle $Spec.task_path $Spec.task_name 60
            }
            $validateArgs = @('-NoLogo', '-NoProfile', '-File', [string]$Spec.staged)
            if ($Target -eq 'HealthTask') { $validateArgs += @('-ConfigPath', $ConfigPath) }
            if ($Target -eq 'DailyBaselineTask') { $validateArgs += @('-ProjectRoot', $Root) }
            $validateArgs += '-ValidateOnly'
            $validation = @(& $PwshPath @validateArgs 2>&1)
            if ($LASTEXITCODE -ne 0) { throw "Staged task wrapper validation failed: $($validation -join ' ')" }
            Install-FileAtomically -Source $Spec.staged -Destination $Spec.destination
            $action = New-ScheduledTaskAction -Execute $PwshPath -Argument $desiredTaskArguments
            Set-ScheduledTask -TaskPath $Spec.task_path -TaskName $Spec.task_name -Action $action | Out-Null
            if ($taskWasEnabled) { Enable-ScheduledTask -TaskPath $Spec.task_path -TaskName $Spec.task_name | Out-Null }
            $afterTask = Get-ExactTask $Spec.task_path $Spec.task_name
            $afterAction = @($afterTask.Actions)[0]
            if ([string]$afterAction.Execute -ine $PwshPath -or [string]$afterAction.Arguments -cne $desiredTaskArguments) {
                throw "Migrated task action verification failed for $($Spec.task_path)$($Spec.task_name)."
            }
            $validation = @(& $PwshPath @validateArgs 2>&1)
            if ($LASTEXITCODE -ne 0) { throw "Installed task wrapper validation failed: $($validation -join ' ')" }
        } else {
            $task = Get-ExactTask $Spec.task_path $Spec.task_name
            Assert-TaskIdentity $Spec $task
            $LegacyState = Get-TaskStateName $task
            if ($LegacyState -ne 'Ready') { throw "Legacy task must be Ready before first disable; state=$LegacyState" }
            Disable-ScheduledTask -TaskPath $Spec.task_path -TaskName $Spec.task_name | Out-Null
            $afterTask = Get-ExactTask $Spec.task_path $Spec.task_name
            if ((Get-TaskStateName $afterTask) -ne 'Disabled') { throw "Legacy task was not disabled: $($Spec.task_path)$($Spec.task_name)" }
        }

        if ($healthTaskWasEnabled) {
            Enable-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFV4PreviewProxy8093HealthCheck' | Out-Null
        }
        $AfterListeners = Get-ListenerSnapshot
        Assert-ListenerIsolation $BeforeListeners $AfterListeners ($Target -eq 'ServiceWrapper')
        Assert-8093Healthy
        $auditAfter = Get-AuditRecord $Spec
        [ordered]@{
            schema = 'ops.8093.pwsh7-runtime-migration.result.v1'
            requirement_id = $RequirementId
            ok = $true
            mode = $Mode
            target = $Target
            changed = $true
            backup = $backup.directory
            rollback_applied = $false
            before = $auditBefore
            after = $auditAfter
            protected_before = $BeforeListeners
            protected_after = $AfterListeners
        } | ConvertTo-Json -Depth 14
    } catch {
        $firstFailure = $_.Exception.Message
        try {
            $manifest = [IO.File]::ReadAllText($backup.manifest_path, [Text.Encoding]::UTF8) | ConvertFrom-Json
            Restore-FromManifest $manifest
            $rollbackApplied = $true
        } catch {
            $firstFailure = "$firstFailure; rollback_failed=$($_.Exception.Message)"
        }
        $AfterListeners = Get-ListenerSnapshot
        [ordered]@{
            schema = 'ops.8093.pwsh7-runtime-migration.result.v1'
            requirement_id = $RequirementId
            ok = $false
            mode = $Mode
            target = $Target
            changed = $true
            backup = $backup.directory
            rollback_applied = $rollbackApplied
            guard_restored = (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -eq 'Running'
            error = $firstFailure
            protected_before = $BeforeListeners
            protected_after = $AfterListeners
        } | ConvertTo-Json -Depth 12
        exit 2
    }
} finally {
    if ($LockTaken -and $Mutex) {
        try { $Mutex.ReleaseMutex() } catch { }
    }
    if ($Mutex) { $Mutex.Dispose() }
}
