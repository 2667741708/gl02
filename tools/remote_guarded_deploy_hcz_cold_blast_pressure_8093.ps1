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

$RequirementId = 'REQ-HCZ-COLD-BLAST-PRESSURE-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_cold_blast_pressure_20260811'
$DeltaPlanPath = Join-Path $StageRoot 'delta-plan.json'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\hcz_cold_blast_pressure_8093_$Stamp"

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid -Port $Port }
    return $Map
}

function Wait-ServiceState {
    param([string]$Desired, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$ServiceName did not reach $Desired."
}

function Wait-PortState {
    param([bool]$Listening, [int]$TimeoutSeconds = 45)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port 8093) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port 8093 did not reach listening=$Listening."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 stop failed.' }
    Wait-ServiceState -Desired 'Stopped'
    Wait-PortState -Listening $false
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 start failed.' }
    Wait-ServiceState -Desired 'Running'
    Wait-PortState -Listening $true
}

function Assert-BelowRoot {
    param([string]$Path)
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    if (-not $ResolvedPath.StartsWith($ResolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escapes production root: $Path"
    }
}

function Install-Atomically {
    param([string]$Source, [string]$Target)
    Assert-BelowRoot -Path $Target
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($DeltaPlanPath, $Manager, $ConfigPath, $Pwsh)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing deployment input: $Required" }
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
    }
})
if ($Files.Count -ne 1) { throw "Expected exactly one configuration delta, received $($Files.Count)." }
foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    if (-not $File.Target.EndsWith('炉况规则引擎\config\hcz_upward_expert_rule.yaml')) { throw 'Delta target is outside the approved HCZ configuration file.' }
    if (-not (Test-Path -LiteralPath $File.Stage -PathType Leaf)) { throw "Missing staged file: $($File.Stage)" }
    if (-not (Test-Path -LiteralPath $File.Target -PathType Leaf)) { throw "Missing production target: $($File.Target)" }
    $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
    $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
    if ($StageHash -ne $File.DesiredHash) { throw 'Staged hash does not match sealed desired hash.' }
    if ($File.BaselineHashes -notcontains $TargetHash) { throw "Unreviewed production baseline: $TargetHash" }
    $StagedText = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
    foreach ($Marker in $File.Markers) {
        if (-not $StagedText.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
    if ($StagedText.Contains('variables: [P_blast]')) { throw 'Staged config still uses hot-blast pressure.' }
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
$BackupPath = $null
$InstalledHashes = [ordered]@{}

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment owns the global mutex.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before deployment." }
    }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 service is not running before deployment.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw '8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    $Target = $Files[0].Target
    $BackupPath = Join-Path $BackupRoot '炉况规则引擎\config\hcz_upward_expert_rule.yaml'
    New-Item -ItemType Directory -Path (Split-Path -Parent $BackupPath) -Force | Out-Null
    Copy-Item -LiteralPath $Target -Destination $BackupPath -Force

    Stop-8093
    $GuardPaused = $true
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid -Port ([int]$Key)) -ne $ProtectedBefore[$Key]) { throw "Protected port $Key changed while 8093 was paused." }
    }

    Install-Atomically -Source $Files[0].Stage -Target $Target
    $InstalledHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    if ($InstalledHash -ne $Files[0].DesiredHash) { throw 'Installed configuration hash mismatch.' }
    $InstalledHashes[$Target] = $InstalledHash

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not restart with a new listener PID.' }

    $Api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/hcz-upward-rule?deploy=$Stamp" -TimeoutSec 120
    if (-not $Api.ok -or $Api.metrics.blast_pressure.label -ne '冷风风压') { throw 'HCZ API did not expose the cold-blast pressure label.' }
    if ([double]$Api.metrics.blast_pressure.threshold -ne 5.0 -or $Api.metrics.blast_pressure.direction -ne 'increase') { throw 'HCZ cold-blast threshold contract changed.' }
    $InstalledText = Get-Content -LiteralPath $Target -Raw -Encoding UTF8
    if (-not $InstalledText.Contains('variables: [P_blast_cold]') -or $InstalledText.Contains('variables: [P_blast]')) { throw 'Installed HCZ variable source is not cold-blast pressure.' }
    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/hcz_upward_rule.html?deploy=$Stamp" -TimeoutSec 30
    $Main = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or $Main.StatusCode -ne 200) { throw '8093 HTTP acceptance failed.' }

    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [pscustomobject]@{
        ok = $true
        notify_immediately = $true
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
        api_pressure_label = [string]$Api.metrics.blast_pressure.label
        api_pressure_delta = $Api.metrics.blast_pressure.delta
        api_pressure_threshold = $Api.metrics.blast_pressure.threshold
        api_status = [string]$Api.status
    } | ConvertTo-Json -Depth 8
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
        if ($BackupPath -and (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
            Copy-Item -LiteralPath $BackupPath -Destination $Files[0].Target -Force
            $RollbackApplied = $true
        }
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
