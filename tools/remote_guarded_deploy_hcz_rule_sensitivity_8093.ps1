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

$RequirementId = 'REQ-HCZ-RULE-SENSITIVITY-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_rule_sensitivity_20260811'
$DeltaPlanPath = Join-Path $StageRoot 'delta-plan.json'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\hcz_rule_sensitivity_8093_$Stamp"
$AllowedTargets = @(
    (Join-Path $Root '炉况规则引擎\features\hcz_upward_expert_rule.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'),
    (Join-Path $Root '高炉前端数据\hcz_upward_rule.html'),
    (Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.js'),
    (Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.css')
)

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

function Assert-AllowedTarget {
    param([string]$Path)
    $Resolved = [IO.Path]::GetFullPath($Path)
    if ($AllowedTargets -notcontains $Resolved) { throw "Target is not allowlisted: $Path" }
}

function Install-Atomically {
    param([string]$Source, [string]$Target)
    Assert-AllowedTarget -Path $Target
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($DeltaPlanPath, $Manager, $ConfigPath, $Pwsh, $Python)) {
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
if ($Files.Count -lt 1 -or $Files.Count -gt $AllowedTargets.Count) {
    throw "Unexpected HCZ sensitivity delta count: $($Files.Count)."
}
foreach ($File in $Files) {
    Assert-AllowedTarget -Path $File.Target
    if (-not (Test-Path -LiteralPath $File.Stage -PathType Leaf)) { throw "Missing staged file: $($File.Stage)" }
    if (-not (Test-Path -LiteralPath $File.Target -PathType Leaf)) { throw "Missing production target: $($File.Target)" }
    $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
    $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
    if ($StageHash -ne $File.DesiredHash) { throw "Staged hash mismatch: $($File.Stage)" }
    if ($File.BaselineHashes -notcontains $TargetHash) { throw "Unreviewed production baseline: $TargetHash" }
    $Text = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
    foreach ($Marker in $File.Markers) {
        if (-not $Text.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
}
& $Python -m py_compile @($Files | Where-Object { $_.Stage.EndsWith('.py') } | ForEach-Object { $_.Stage })
if ($LASTEXITCODE -ne 0) { throw 'Staged Python syntax validation failed.' }

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
    if (-not $MutexAcquired) { throw 'Another 8093 deployment owns the global mutex.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before deployment." }
    }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 service is not running before deployment.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw '8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = [IO.Path]::GetRelativePath($Root, $File.Target)
        $Backup = Join-Path $BackupRoot $Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
        Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        $Previous[$File.Target] = $Backup
    }

    Stop-8093
    $GuardPaused = $true
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid -Port ([int]$Key)) -ne $ProtectedBefore[$Key]) { throw "Protected port $Key changed while 8093 was paused." }
    }
    foreach ($File in $Files) {
        Install-Atomically -Source $File.Stage -Target $File.Target
        $InstalledHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($InstalledHash -ne $File.DesiredHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $InstalledHash
    }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not restart with a new listener PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/hcz_upward_rule.html?deploy=$Stamp" -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains('REQ-HCZ-RULE-SENSITIVITY-20260811')) {
        throw 'HCZ sensitivity page marker verification failed.'
    }
    $Api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/hcz-upward-rule?deploy=$Stamp" -TimeoutSec 120
    if (-not $Api.ok -or -not $Api.source.gas_utilisation_normalised -or $Api.metrics.blast_pressure.label -ne '冷风风压') {
        throw 'HCZ current-rule API contract verification failed.'
    }
    $SensitivityUri = "http://127.0.0.1:8093/api/hcz-rule-sensitivity?days=90&top_temperature_delta_c=10&deploy=$Stamp"
    $Trial = Invoke-RestMethod -Uri $SensitivityUri -TimeoutSec 300
    if (-not $Trial.ok -or -not $Trial.read_only_trial -or $Trial.production_defaults_changed) { throw 'HCZ trial safety contract failed.' }
    if ([double]$Trial.parameters.baseline.top_temperature_delta_c -ne 15.0 -or [double]$Trial.parameters.scenario.top_temperature_delta_c -ne 10.0) {
        throw 'HCZ top-temperature sensitivity parameters are incorrect.'
    }
    if (-not $Trial.source.read_only -or -not $Trial.source.gas_utilisation_normalised) { throw 'HCZ trial source is not read-only or unit-normalised.' }
    if ($Trial.safety.downward_definition -ne 'symmetric_mirror_candidate_only' -or $Trial.safety.automatic_control -ne 'prohibited') {
        throw 'HCZ downward-candidate safety boundary failed.'
    }
    $Main = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -TimeoutSec 30
    if ($Main.StatusCode -ne 200) { throw '8093 main page verification failed.' }

    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [ordered]@{
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
        artifact_count_delta = $Files.Count
        http_8093 = [int]$Page.StatusCode
        api_status = [string]$Api.status
        gas_utilisation_delta_pp = $Api.metrics.gas_utilisation.delta
        sensitivity = [ordered]@{
            history_days = [int]$Trial.history_days
            evaluation_start = [string]$Trial.evaluation_start
            evaluation_end = [string]$Trial.evaluation_end
            baseline_up_episodes = [int]$Trial.baseline.up.episode_count
            scenario_up_episodes = [int]$Trial.scenario.up.episode_count
            baseline_down_episodes = [int]$Trial.baseline.down.episode_count
            scenario_down_episodes = [int]$Trial.scenario.down.episode_count
            added_up_hours = [int]$Trial.comparison.up.added_triggered_hour_count
            evaluation_elapsed_ms = [int]$Trial.source.evaluation_elapsed_ms
        }
    } | ConvertTo-Json -Depth 9
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
        foreach ($Target in $Previous.Keys) {
            Copy-Item -LiteralPath $Previous[$Target] -Destination $Target -Force
        }
        if ($Previous.Count -gt 0) { $RollbackApplied = $true }
    }
    finally {
        if ($Old8093Pid) {
            Start-8093
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
        listener_8093 = Get-ListenerPid -Port 8093
    } | ConvertTo-Json -Depth 5 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
