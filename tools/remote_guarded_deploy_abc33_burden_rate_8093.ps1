$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-ABC33-BURDEN-THREE-FACTOR-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_burden_three_factor_20260811_v1'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\abc33_burden_rate_8093_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$Files = @(
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'abc_burden_rate.py'; Target = Join-Path $Root '自动诊断服务\abc_burden_rate.py'; BaselineHashes = @('62E9CE3F3AA9153BED90295F73086D16ABF9073BFB710AE0BDBB459AC19DCE54'); Markers = @('BurdenRateHalfHourDev','BurdenRateYesterdayDev','BurdenRate2hDev'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'abc_factor_audit.py'; Target = Join-Path $Root '自动诊断服务\abc_factor_audit.py'; BaselineHashes = @('B9844CF695907A13C82A92F76220289535240FDEA2B2061B39EB44DAF9F651B1'); Markers = @('BurdenRateHalfHourDev'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'abc_feature_builder.py'; Target = Join-Path $Root '自动诊断服务\abc_feature_builder.py'; BaselineHashes = @('094A917353202F6BF248137652E4FF7C2E925EDDCBCBA929C8714BDBEEF102EE'); Markers = @('BurdenRate2hFast'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'abc_rule_catalog.py'; Target = Join-Path $Root '自动诊断服务\abc_rule_catalog.py'; BaselineHashes = @('E28F932EC1CFB3DC65C3BC07B2FC8C4523981D4A50E66B5F690C1D13C24564F4'); Markers = @('"BurdenRateHalfHourDev":14','"BurdenRateYesterdayDev":4','"BurdenRate2hDev":2'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'abc_term_semantics.py'; Target = Join-Path $Root '自动诊断服务\abc_term_semantics.py'; BaselineHashes = @('F5EBCA20EE32419FDE99FCE3F160E72199157A6DD75C5AEB7974D04BF70EDA76'); Markers = @('前后30分钟料速偏差','连续2小时料速偏快'); AllowCreate = $false }
)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedPortMap {
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
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 stop failed.' }
    Wait-ServiceState -Name $ServiceName -Desired 'Stopped'
    Wait-PortState -Port 8093 -Listening $false
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Managed 8093 start failed.' }
    Wait-ServiceState -Name $ServiceName -Desired 'Running' -TimeoutSeconds 60
    Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 60
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

foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $Python) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing deployment input: $Required" }
}
foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
    if (-not $Exists -and -not $File.AllowCreate) { throw "Production target missing: $($File.Target)" }
    if ($Exists) {
        $Hash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($File.BaselineHashes -notcontains $Hash) { throw "Unreviewed baseline: $($File.Target) $Hash" }
    }
    $StagedText = Get-Content -LiteralPath $File.Stage -Raw -Encoding UTF8
    foreach ($Marker in $File.Markers) {
        if (-not $StagedText.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
}

$StagedPython = @($Files | Where-Object { $_.Stage.EndsWith('.py') } | ForEach-Object { $_.Stage })
& $Python -m py_compile @StagedPython
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
$Page = $null
$A2 = $null
$B4 = $null
$B5 = $null

try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8093 deployment or recovery owns the deployment mutex.' }

    $ProtectedBefore = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before deployment." }
    }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 is not running before deployment.' }
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
        if ($TargetHash -ne $StageHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $TargetHash
    }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not start with a new listener PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=abc33-burden-rate-$Stamp#optimization" -TimeoutSec 45
    if ($Page.StatusCode -ne 200) { throw '8093 HTTP verification failed.' }
    $A2 = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/furnace-rules/A2/detail?cb=$Stamp" -TimeoutSec 90
    $B4 = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/furnace-rules/B4/detail?cb=$Stamp" -TimeoutSec 90
    $B5 = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/furnace-rules/B5/detail?cb=$Stamp" -TimeoutSec 90
    foreach ($Pair in @(@('A2', $A2), @('B4', $B4), @('B5', $B5))) {
        $RuleId = $Pair[0]
        $Response = $Pair[1]
        if (-not $Response.ok -or $Response.sensor_review.schema_version -ne 'furnace_rule_sensor_review.v2') {
            throw "$RuleId detail API did not return the reviewed sensor contract."
        }
        $FirstMetric = @($Response.sensor_review.main_metrics)[0]
        if ($FirstMetric.variable_name -ne 'BurdenRate_large_per_hour' -or $FirstMetric.label -ne '探尺识别料速（完整大批）') {
            throw "$RuleId did not expose burden rate as the first operator review metric."
        }
        $Serialized = $Response | ConvertTo-Json -Depth 20 -Compress
        foreach ($Forbidden in @('formula_terms', 'normalized_value', 'contribution', 'feature_thresholds')) {
            if ($Serialized.Contains($Forbidden)) { throw "$RuleId public API leaked internal field $Forbidden." }
        }
    }

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
        http_8093 = [int]$Page.StatusCode
        detail_checks = [ordered]@{
            A2 = @($A2.sensor_review.main_metrics)[0].data_state
            B4 = @($B4.sensor_review.main_metrics)[0].data_state
            B5 = @($B5.sensor_review.main_metrics)[0].data_state
        }
    } | ConvertTo-Json -Depth 8
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
