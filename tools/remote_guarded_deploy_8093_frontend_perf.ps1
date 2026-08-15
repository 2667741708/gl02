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

$RequirementId = 'REQ-8093-FRONTEND-PERF-R1'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$WsServiceName = 'BFV4PreviewWs8768'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\8093_frontend_perf_r1_20260810'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\8093_frontend_perf_r1_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)
$Files = @(
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'; Target = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'; BaselineHashes = @('8CA9139613981F3950C3C3D8ECC50DDA6FC1E619D77B6DAB202E6067C9061064'); Markers = @('REQ-8093-FRONTEND-PERF-R1', 'dashboard-main-v9ebK4cf.js', 'overview-route-loader-Bv2DvOlP.js'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'dashboard-main-v9ebK4cf.js'; Target = Join-Path $Root '高炉前端数据\assets\build\dashboard-main-v9ebK4cf.js'; BaselineHashes = @('0DAD8EEB8B453F5093D8EAAFA8369B87E3C33DA01DBE2CE4186C4563BFD04475'); Markers = @('19个核心变量趋势与预测', 'GL02_FURNACE_BODY_R1.glb'); AllowCreate = $true },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'overview-route-loader-Bv2DvOlP.js'; Target = Join-Path $Root '高炉前端数据\assets\build\overview-route-loader-Bv2DvOlP.js'; BaselineHashes = @('3DE19416A94C1CC96E07AD810EB1AA6853838600F40B6A9FBC86294C14DDA399'); Markers = @('bf.overview.route-loader.v1', '20260810-perf-r1'); AllowCreate = $true },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf-shared-runtime-scheduler.js'; Target = Join-Path $Root '高炉前端数据\assets\bf-shared-runtime-scheduler.js'; BaselineHashes = @('E52E03A257AC892CB4BAE6C56011E05AE2BC961DB301FC7EC865DE5297E5BF73'); Markers = @('bf.shared-runtime-scheduler.v1'); AllowCreate = $true },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf-core-metrics-pspace-live-8093.js'; Target = Join-Path $Root '高炉前端数据\assets\bf-core-metrics-pspace-live-8093.js'; BaselineHashes = @('33195006D8F7C618C9904F540D27A4589A829A6F2FA08A03E4F3900F5C38E338'); Markers = @('bf:pspace-frame'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf3d-furnace-body-billboard-adapter.js'; Target = Join-Path $Root '高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js'; BaselineHashes = @('8E5FB80F1D4A4A22DB5811E6B1A379867C5C50B1B4D1FD59EB74CA0569144E60'); Markers = @('bf3d.sensor_billboard.runtime.v1', 'bf:pspace-frame'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf3d-physical-point-filter-8093.js'; Target = Join-Path $Root '高炉前端数据\assets\bf3d-physical-point-filter-8093.js'; BaselineHashes = @('EDD9DE6702BAA19EFEA926A0ABF30C52DDF261FFCD719AAE358D28FC43E50CD0'); Markers = @('measured-121-8093'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'bf3d-surface-camera-guard-8093.js'; Target = Join-Path $Root '高炉前端数据\assets\bf3d-surface-camera-guard-8093.js'; BaselineHashes = @('1C87B11B934392CC026FDE3B45819664170355DBCA9E0DD2CF3B735BC16DC6F0'); Markers = @('bf3d.camera.overview-only.8093.v4'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'ollama_proxy_server.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'; BaselineHashes = @('8A69CECA910E3D088C13F659E91C24146F5ED355F29D5F9C332E1831B103B5D0'); Markers = @('compress_static_payload'); AllowCreate = $false },
    [pscustomobject]@{ Stage = Join-Path $StageRoot 'http_static_compression.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\http_static_compression.py'; BaselineHashes = @('1F5EC14689FE32340A0F49E519A8D985A371314EE9C858329E39B230B8D861C0'); Markers = @('REQ-8093-FRONTEND-PERF-R1', 'BF_HTTP_COMPRESSION_MIN_BYTES'); AllowCreate = $true }
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

function Install-FileAtomically {
    param([string]$Source, [string]$Target)
    Assert-BelowRoot -Path $Target
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

function Get-HttpRepresentation {
    param([string]$Uri, [string]$AcceptEncoding = 'identity')
    $Handler = [Net.Http.HttpClientHandler]::new()
    $Handler.AutomaticDecompression = [Net.DecompressionMethods]::None
    $Client = [Net.Http.HttpClient]::new($Handler)
    $Client.Timeout = [TimeSpan]::FromSeconds(30)
    $Request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Get, $Uri)
    [void]$Request.Headers.TryAddWithoutValidation('Accept-Encoding', $AcceptEncoding)
    try {
        $Response = $Client.Send($Request)
        $Bytes = $Response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        return [pscustomobject]@{
            status = [int]$Response.StatusCode
            encoding = (@($Response.Content.Headers.ContentEncoding) -join ',')
            cache_control = [string]$Response.Headers.CacheControl
            vary = (@($Response.Headers.Vary) -join ',')
            etag = [string]$Response.Headers.ETag
            length = $Bytes.Length
            body = if ($AcceptEncoding -eq 'identity') { [Text.Encoding]::UTF8.GetString($Bytes) } else { '' }
        }
    }
    finally {
        $Request.Dispose()
        $Client.Dispose()
        $Handler.Dispose()
    }
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
& $Python -m py_compile (Join-Path $StageRoot 'ollama_proxy_server.py') (Join-Path $StageRoot 'http_static_compression.py')
if ($LASTEXITCODE -ne 0) { throw 'Staged Python syntax validation failed.' }

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$MutexAcquired = $false
$GuardPaused = $false
$GuardRestored = $false
$RollbackApplied = $false
$InstallStarted = $false
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
    if ((Get-Service -Name $WsServiceName).Status -ne 'Running') { throw '8768 managed service is not running before deployment.' }
    $Old8093Pid = Get-ListenerPid -Port 8093
    if (-not $Old8093Pid) { throw 'Port 8093 is not listening before deployment.' }

    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Relative = $File.Target.Substring($Root.Length).TrimStart('\')
        $Backup = Join-Path $BackupRoot $Relative
        $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
        $OriginalHash = if ($Exists) { (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash } else { $null }
        $Previous[$File.Target] = @{ Existed = $Exists; Backup = $Backup; Hash = $OriginalHash }
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

    $Main = Get-HttpRepresentation -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -AcceptEncoding 'identity'
    if ($Main.status -ne 200 -or -not $Main.body.Contains('REQ-8093-FRONTEND-PERF-R1')) { throw '8093 production-build marker verification failed.' }
    if ($Main.body.Contains('babel.min.js') -or $Main.body.Contains('react.development.js')) { throw 'Development browser runtime remains in the served page.' }
    $MainAsset = Get-HttpRepresentation -Uri "http://127.0.0.1:8093/assets/build/dashboard-main-v9ebK4cf.js?deploy=$Stamp" -AcceptEncoding 'br'
    if ($MainAsset.status -ne 200 -or $MainAsset.encoding -ne 'br') { throw 'Brotli representation verification failed.' }
    if (-not $MainAsset.cache_control.Contains('immutable') -or -not $MainAsset.etag) { throw 'Hashed asset cache contract verification failed.' }
    if ($MainAsset.length -ge 609491) { throw 'Brotli response was not smaller than the source asset.' }
    $CoreAsset = Get-HttpRepresentation -Uri "http://127.0.0.1:8093/assets/bf-core-metrics-pspace-live-8093.js?v=20260810-perf-r1" -AcceptEncoding 'gzip'
    if ($CoreAsset.status -ne 200 -or $CoreAsset.encoding -ne 'gzip') { throw 'Gzip representation verification failed.' }
    if (-not $CoreAsset.cache_control.Contains('immutable')) { throw 'Versioned runtime cache contract verification failed.' }

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
        http_8093 = $Main.status
        compression = @{ brotli = $MainAsset.encoding; gzip = $CoreAsset.encoding }
        cache = @{ hashed = $MainAsset.cache_control; versioned = $CoreAsset.cache_control }
    } | ConvertTo-Json -Depth 8
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($InstallStarted) {
            if ((Get-Service -Name $ServiceName).Status -ne 'Stopped') { Stop-8093 }
            foreach ($Target in $Previous.Keys) {
                Assert-BelowRoot -Path $Target
                $State = $Previous[$Target]
                if ($State.Existed) {
                    Install-FileAtomically -Source $State.Backup -Target $Target
                    $RestoredHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
                    if ($RestoredHash -ne $State.Hash) { throw "Rollback hash mismatch: $Target" }
                }
                elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                    Remove-Item -LiteralPath $Target -Force
                    if (Test-Path -LiteralPath $Target -PathType Leaf) { throw "Rollback could not remove created target: $Target" }
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
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
        protected_after = Get-ProtectedPortMap
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
