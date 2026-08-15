$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-8093-ABC33-OVERVIEW-ENTRY-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_overview_entry_20260811'
$DeltaPlanPath = Join-Path $StageRoot 'delta-plan.json'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\abc33_overview_entry_8093_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
if (-not (Test-Path -LiteralPath $DeltaPlanPath -PathType Leaf)) {
    throw "Missing delta plan: $DeltaPlanPath"
}
$DeltaPlan = Get-Content -LiteralPath $DeltaPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($DeltaPlan.schema -ne 'bf.deploy.delta-plan.v1' -or $DeltaPlan.requirement_id -ne $RequirementId) {
    throw 'Delta plan schema or requirement mismatch.'
}
$Files = @($DeltaPlan.changes | ForEach-Object {
    [pscustomobject]@{
        Stage = [string]$_.stage
        Target = [string]$_.target
        DesiredHash = [string]$_.desired_sha256
        BaselineHashes = @($_.baseline_sha256 | ForEach-Object { [string]$_ })
        Markers = @($_.markers | ForEach-Object { [string]$_ })
        AllowCreate = [bool]$_.allow_create
    }
})
if ($Files.Count -eq 0) { throw 'Delta plan is empty; do not restart 8093.' }

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedPortMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid -Port $Port }
    return $Map
}

function Wait-ServiceState {
    param([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 40)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$Name did not reach $Desired within $TimeoutSeconds seconds."
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 40)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening within $TimeoutSeconds seconds."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Name $ServiceName -Desired 'Stopped'
    Wait-PortState -Port 8093 -Listening $false
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Name $ServiceName -Desired 'Running'
    Wait-PortState -Port 8093 -Listening $true
}

function Assert-BelowRoot {
    param([string]$Path)
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $ResolvedPath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escapes production root: $Path"
    }
}

function Install-FileAtomically {
    param([string]$Source, [string]$Target)
    Assert-BelowRoot -Path $Target
    $Directory = Split-Path -Parent $Target
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

if (($RequirementId + $StageRoot).Contains('__')) {
    throw 'Deployment template still contains unresolved placeholders.'
}
foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $DeltaPlanPath) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    $ResolvedStageRoot = [IO.Path]::GetFullPath($StageRoot).TrimEnd('\') + '\'
    $ResolvedStage = [IO.Path]::GetFullPath($File.Stage)
    if (-not $ResolvedStage.StartsWith($ResolvedStageRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Stage path escapes approved stage root: $($File.Stage)"
    }
    $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
    if ($StageHash -ne $File.DesiredHash) { throw "Staged desired hash mismatch: $($File.Stage)" }
    $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
    if (-not $Exists -and -not $File.AllowCreate) { throw "Production target missing: $($File.Target)" }
    if ($Exists) {
        $Hash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($File.BaselineHashes -notcontains $Hash) { throw "Unreviewed baseline: $($File.Target) $Hash" }
    }
    if ($File.Markers.Count -gt 0) {
        $StagedText = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
        foreach ($Marker in $File.Markers) {
            if (-not $StagedText.Contains($Marker)) { throw "Staged marker missing: $Marker" }
        }
    }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAcquired = $false
$GuardPaused = $false
$GuardRestored = $false
$RollbackApplied = $false
$Old8093Pid = $null
$New8093Pid = $null
$ProtectedBefore = $null
$ProtectedAfter = $null
$Previous = @{}
$InstalledHashes = [ordered]@{}

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment or recovery owns the deployment mutex.' }

    $ProtectedBefore = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before deployment." }
    }
    if ((Get-Service -Name $ServiceName).Status -ne 'Running') { throw '8093 is not running before deployment.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw 'Port 8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = $File.Target.Substring($Root.Length).TrimStart('\')
        $Backup = Join-Path $BackupRoot $Relative
        $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
        $Previous[$File.Target] = @{ Existed = $Exists; Backup = $Backup }
        if ($Exists) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
            Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        }
    }

    Stop-8093
    $GuardPaused = $true
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid -Port ([int]$Key)) -ne $ProtectedBefore[$Key]) {
            throw "Protected port $Key changed while 8093 was paused."
        }
    }

    foreach ($File in $Files) {
        Install-FileAtomically -Source $File.Stage -Target $File.Target
        $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
        $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($TargetHash -ne $StageHash -or $TargetHash -ne $File.DesiredHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $TargetHash
    }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not start with a new listener PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -TimeoutSec 30
    if ($Page.StatusCode -ne 200) { throw '8093 HTTP verification failed.' }
    $Asset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=abc33-20260811-overview-entry-r1&deploy=$Stamp" -TimeoutSec 30
    if (-not $Page.Content.Contains('abc33-20260811-overview-entry-r1')) { throw '8093 page cache version marker missing.' }
    if (-not $Asset.Content.Contains('BUG-8093-ABC33-OVERVIEW-ENTRY-20260811')) { throw 'ABC33 overview-entry asset marker missing.' }
    if (-not $Asset.Content.Contains("overview-furnace-panel-v12 > .panel-head")) { throw 'ABC33 overview panel anchor missing.' }
    if ($Asset.Content.Contains('abc33-entry-fallback')) { throw 'Forbidden fixed fallback remains in served asset.' }

    $ProtectedAfter = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [pscustomobject]@{
        ok = $true
        requirement_id = $RequirementId
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        installed_hashes = $InstalledHashes
        delta_plan_sha256 = (Get-FileHash -LiteralPath $DeltaPlanPath -Algorithm SHA256).Hash
        artifact_count_delta = $Files.Count
        http_8093 = [int]$Page.StatusCode
    } | ConvertTo-Json -Depth 7
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
        foreach ($Target in $Previous.Keys) {
            Assert-BelowRoot -Path $Target
            $State = $Previous[$Target]
            if ($State.Existed) {
                Copy-Item -LiteralPath $State.Backup -Destination $Target -Force
            }
            elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                Remove-Item -LiteralPath $Target -Force
            }
        }
        if ($Previous.Count -gt 0) { $RollbackApplied = $true }
    }
    finally {
        if ($Old8093Pid) {
            Start-8093
            $GuardRestored = $true
        }
    }
    [pscustomobject]@{
        ok = $false
        requirement_id = $RequirementId
        failure = $Failure
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
    } | ConvertTo-Json -Depth 5 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
