[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-REMOVE-THROAT-RESTORE-HEAT-QUERY-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\8093_remove_throat_restore_query_20260811'
$ServiceName = 'BFV4PreviewProxy8093'
$WsServiceName = 'BFV4PreviewWs8768'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\8093_remove_throat_restore_query_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Files = @(
    [pscustomobject]@{
        Stage = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
        Target = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
        BaselineHashes = @('3F4E38ABB6E2A6360E4FB27602E406AD66BA3D285E40947F5BA67239733BD08D')
        DesiredHash = 'D81DD7B4471140A3289BE0574BBC46FFB9AEBEF41B1434AF6EF1409D6545ED75'
        Markers = @('REQ-8093-FRONTEND-PERF-R1', 'dashboard-main-GX_5dx5H.js', 'bf-heat-performance-quality-8093-query-v2.js?v=20260807-query-v2')
        AllowCreate = $false
    },
    [pscustomobject]@{
        Stage = Join-Path $StageRoot 'dashboard-main-GX_5dx5H.js'
        Target = Join-Path $Root '高炉前端数据\assets\build\dashboard-main-GX_5dx5H.js'
        BaselineHashes = @()
        DesiredHash = '7FDE5A8E789437FA45AF003DF990AEB10310A7E1A7BE730A01F930BFDF9BDD4C'
        Markers = @('no-throat-temperature-20260811', 'data-core-variable-id', 'GL02_FURNACE_BODY_R1.glb')
        AllowCreate = $true
    },
    [pscustomobject]@{
        Stage = Join-Path $StageRoot 'bf-heat-performance-quality-8093-query-v2.js'
        Target = Join-Path $Root '高炉前端数据\assets\bf-heat-performance-quality-8093-query-v2.js'
        BaselineHashes = @()
        DesiredHash = 'D8435BFAB5C25093E22C9909846C426679B30BD14155AF061BD711D7656527A1'
        Markers = @('REQ-8093-HEAT-PERFORMANCE-QUALITY-QUERY-20260807', '/api/heat-performance-quality')
        AllowCreate = $true
    }
)

function Get-ListenerPid([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid $Port }
    return $Map
}

function Wait-ServiceState([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 60) {
    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "$Name did not reach $Desired."
}

function Wait-Port([bool]$Listening, [int]$TimeoutSeconds = 60) {
    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (($null -ne (Get-ListenerPid 8093)) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw "8093 did not reach listening=$Listening."
}

function Invoke-ServiceAction([ValidateSet('stop', 'start')] [string]$Action) {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action $Action -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Managed service action failed: $Action" }
}

function Assert-BelowRoot([string]$Path) {
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $ResolvedPath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escapes production root: $Path"
    }
}

function Install-Atomic([string]$Source, [string]$Target) {
    Assert-BelowRoot $Target
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($Pwsh, $Manager, $ConfigPath) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing deployment input: $Required" }
}
foreach ($File in $Files) {
    Assert-BelowRoot $File.Target
    if ((Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash -ne $File.DesiredHash) {
        throw "Staged hash mismatch: $($File.Stage)"
    }
    $Text = [IO.File]::ReadAllText($File.Stage, [Text.Encoding]::UTF8)
    foreach ($Marker in $File.Markers) {
        if (-not $Text.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
    $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
    if (-not $Exists -and -not $File.AllowCreate) { throw "Production target missing: $($File.Target)" }
    if ($Exists) {
        $CurrentHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($CurrentHash -ne $File.DesiredHash -and $File.BaselineHashes -notcontains $CurrentHash) {
            throw "Unreviewed production baseline: $($File.Target) $CurrentHash"
        }
    }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$LockTaken = $false
$GuardPaused = $false
$GuardRestored = $false
$InstallStarted = $false
$RollbackApplied = $false
$Previous = @{}
$ProtectedBefore = $null
$Old8093Pid = $null

try {
    $LockTaken = $Mutex.WaitOne(0)
    if (-not $LockTaken) { throw 'Another 8093 deployment owns the deployment mutex.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port is missing: $Key" }
    }
    if ((Get-Service -Name $ServiceName).Status -ne 'Running') { throw '8093 service is not Running.' }
    if ((Get-Service -Name $WsServiceName).Status -ne 'Running') { throw '8768 service is not Running.' }
    $Old8093Pid = Get-ListenerPid 8093
    if (-not $Old8093Pid) { throw '8093 listener is missing.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = $File.Target.Substring($Root.Length).TrimStart('\')
        $Backup = Join-Path $BackupRoot $Relative
        $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
        $Previous[$File.Target] = @{
            Existed = $Exists
            Backup = $Backup
            Hash = if ($Exists) { (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash } else { $null }
        }
        if ($Exists) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
            Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        }
    }

    Invoke-ServiceAction stop
    Wait-ServiceState $ServiceName 'Stopped'
    Wait-Port $false
    $GuardPaused = $true
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid ([int]$Key)) -ne $ProtectedBefore[$Key]) { throw "Protected PID changed while paused: $Key" }
    }

    $InstallStarted = $true
    foreach ($File in $Files) {
        Install-Atomic $File.Stage $File.Target
        if ((Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash -ne $File.DesiredHash) {
            throw "Installed hash mismatch: $($File.Target)"
        }
    }

    Invoke-ServiceAction start
    Wait-ServiceState $ServiceName 'Running'
    Wait-Port $true
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid 8093
    if ($New8093Pid -eq $Old8093Pid) { throw '8093 listener PID did not change.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$Stamp#diagnosis" -TimeoutSec 30
    if ([int]$Page.StatusCode -ne 200 -or -not ([string]$Page.Content).Contains('dashboard-main-GX_5dx5H.js')) {
        throw 'Served HTML acceptance failed.'
    }
    $Main = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/build/dashboard-main-GX_5dx5H.js?cb=$Stamp" -TimeoutSec 30
    if ([int]$Main.StatusCode -ne 200 -or -not ([string]$Main.Content).Contains('no-throat-temperature-20260811')) {
        throw 'Served diagnosis bundle acceptance failed.'
    }
    $Query = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf-heat-performance-quality-8093-query-v2.js?v=20260807-query-v2" -TimeoutSec 30
    if ([int]$Query.StatusCode -ne 200 -or -not ([string]$Query.Content).Contains('REQ-8093-HEAT-PERFORMANCE-QUALITY-QUERY-20260807')) {
        throw 'Served heat-query asset acceptance failed.'
    }

    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        backup = $BackupRoot
        mutex_acquired = $LockTaken
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        http = @{ page = [int]$Page.StatusCode; main = [int]$Main.StatusCode; heat_query = [int]$Query.StatusCode }
    } | ConvertTo-Json -Depth 8
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($InstallStarted) {
            if ((Get-Service -Name $ServiceName).Status -ne 'Stopped') {
                Invoke-ServiceAction stop
                Wait-ServiceState $ServiceName 'Stopped'
                Wait-Port $false
            }
            foreach ($Target in $Previous.Keys) {
                $State = $Previous[$Target]
                if ($State.Existed) {
                    Install-Atomic $State.Backup $Target
                    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $State.Hash) {
                        throw "Rollback hash mismatch: $Target"
                    }
                }
                elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                    Remove-Item -LiteralPath $Target -Force
                }
            }
            $RollbackApplied = $true
        }
    }
    finally {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Running') {
            Invoke-ServiceAction start
            Wait-ServiceState $ServiceName 'Running'
            Wait-Port $true
            $GuardRestored = $true
        }
    }
    [ordered]@{
        ok = $false
        requirement_id = $RequirementId
        failure = $Failure
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid 8093
        protected_after = Get-ProtectedMap
    } | ConvertTo-Json -Depth 7 | Write-Output
    throw $Failure
}
finally {
    if ($LockTaken) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
