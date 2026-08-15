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

$RequirementId = 'BUG-8093-CORE-PORTAL-BASELINE-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$WsServiceName = 'BFV4PreviewWs8768'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\8093_core_portal_baseline_20260811'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\8093_core_portal_baseline_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Files = @(
    [pscustomobject]@{
        Stage = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
        Target = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
        BaselineHashes = @('2F92DC7A914E9D29153A137624E3044012B3F8687CC03B5696DCFA04B5968664')
        DesiredHash = '3F4E38ABB6E2A6360E4FB27602E406AD66BA3D285E40947F5BA67239733BD08D'
        Markers = @('REQ-8093-FRONTEND-PERF-R1', 'dashboard-main-CcxwpZA4.js', 'overview-route-loader-Bv2DvOlP.js')
        AllowCreate = $false
    },
    [pscustomobject]@{
        Stage = Join-Path $StageRoot 'dashboard-main-CcxwpZA4.js'
        Target = Join-Path $Root '高炉前端数据\assets\build\dashboard-main-CcxwpZA4.js'
        BaselineHashes = @()
        DesiredHash = 'C57C8EEDD280CA984D253AF8B7E04193B69D481956964A1800EEB9B1439F03DC'
        Markers = @('data-baseline-evidence', '独立30日基线', '核心变量详情 · 只读分析')
        AllowCreate = $true
    }
)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid -Port $Port }
    return $Map
}

function Wait-ServiceState {
    param([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$Name did not reach $Desired within $TimeoutSeconds seconds."
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening within $TimeoutSeconds seconds."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 stop failed.' }
    Wait-ServiceState -Name $ServiceName -Desired 'Stopped'
    Wait-PortState -Port 8093 -Listening $false
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 start failed.' }
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

function Install-Atomic {
    param([string]$Source, [string]$Target)
    Assert-BelowRoot -Path $Target
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($Pwsh, $Manager, $ConfigPath) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing deployment input: $Required" }
}
foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
    if ($StageHash -ne $File.DesiredHash) { throw "Staged hash mismatch: $($File.Stage)" }
    $StageText = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
    foreach ($Marker in $File.Markers) {
        if (-not $StageText.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
    $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
    if (-not $Exists -and -not $File.AllowCreate) { throw "Production target missing: $($File.Target)" }
    if ($Exists) {
        $CurrentHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($CurrentHash -eq $File.DesiredHash) { continue }
        if ($File.BaselineHashes -notcontains $CurrentHash) {
            throw "Unreviewed production baseline: $($File.Target) $CurrentHash"
        }
    }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAcquired = $false
$GuardPaused = $false
$GuardRestored = $false
$InstallStarted = $false
$RollbackApplied = $false
$Old8093Pid = $null
$New8093Pid = $null
$ProtectedBefore = $null
$ProtectedAfter = $null
$Previous = @{}
$InstalledHashes = [ordered]@{}
$Failure = $null

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment or recovery owns the deployment mutex.' }

    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before deployment." }
    }
    if ((Get-Service -Name $ServiceName).Status -ne 'Running') { throw '8093 service is not running before deployment.' }
    if ((Get-Service -Name $WsServiceName).Status -ne 'Running') { throw '8768 managed service is not running before deployment.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw '8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = $File.Target.Substring($Root.Length).TrimStart('\')
        $Backup = Join-Path $BackupRoot $Relative
        $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
        $Hash = if ($Exists) { (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash } else { $null }
        $Previous[$File.Target] = @{ Existed = $Exists; Backup = $Backup; Hash = $Hash }
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

    $InstallStarted = $true
    foreach ($File in $Files) {
        Install-Atomic -Source $File.Stage -Target $File.Target
        $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($TargetHash -ne $File.DesiredHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $TargetHash
    }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not start with a new listener PID.' }

    $Main = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp#overview" -TimeoutSec 30
    if ([int]$Main.StatusCode -ne 200) { throw "8093 page returned HTTP $($Main.StatusCode)." }
    $MainText = [string]$Main.Content
    foreach ($Marker in @('REQ-8093-FRONTEND-PERF-R1', 'dashboard-main-CcxwpZA4.js')) {
        if (-not $MainText.Contains($Marker)) { throw "Served page marker missing: $Marker" }
    }
    if ($MainText.Contains('babel.min.js') -or $MainText.Contains('react.development.js')) {
        throw 'Development browser runtime remains in served HTML.'
    }
    $Asset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/build/dashboard-main-CcxwpZA4.js?deploy=$Stamp" -TimeoutSec 30
    if ([int]$Asset.StatusCode -ne 200) { throw "8093 bundle returned HTTP $($Asset.StatusCode)." }
    $AssetText = [string]$Asset.Content
    foreach ($Marker in @('data-baseline-evidence', '独立30日基线', '核心变量详情 · 只读分析')) {
        if (-not $AssetText.Contains($Marker)) { throw "Served bundle marker missing: $Marker" }
    }
    if (-not ([string]$Asset.Headers['Cache-Control']).Contains('immutable')) {
        throw 'Hashed bundle immutable cache contract is missing.'
    }

    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [pscustomobject]@{
        ok = $true
        requirement_id = $RequirementId
        backup = $BackupRoot
        mutex_acquired = $MutexAcquired
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        installed_hashes = $InstalledHashes
        http_8093 = [int]$Main.StatusCode
        bundle_http_8093 = [int]$Asset.StatusCode
    } | ConvertTo-Json -Depth 8
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($InstallStarted) {
            if ((Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
            foreach ($Target in $Previous.Keys) {
                $State = $Previous[$Target]
                if ($State.Existed) {
                    Install-Atomic -Source $State.Backup -Target $Target
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
            Start-8093
            $GuardRestored = $true
        }
    }
    [pscustomobject]@{
        ok = $false
        requirement_id = $RequirementId
        failure = $Failure
        backup = $BackupRoot
        mutex_acquired = $MutexAcquired
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
        protected_after = Get-ProtectedMap
    } | ConvertTo-Json -Depth 7 | Write-Output
    throw $Failure
}
finally {
    if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Running') {
        try {
            Start-8093
            $GuardRestored = $true
        }
        catch { Write-Error "8093 final restoration failed: $($_.Exception.Message)" }
    }
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
