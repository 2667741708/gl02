[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedManifestSha256,
    [switch]$SkipModelSse,
    [switch]$GuestSharedAcceptance,
    [ValidatePattern('^(REQ|BUG|OPS)-[A-Z0-9._-]+$')]
    [string]$RequirementId = 'REQ-ABC33-CONTEXTUAL-ASSISTANT-POPUP-20260811',
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_context_20260812_prod'
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$DeltaPlanPath = Join-Path $StageRoot 'delta-plan.json'
$MigrationPath = Join-Path $StageRoot '20260811_abc_contextual_assistant.sql'
$AcceptancePath = Join-Path $StageRoot 'remote_accept_abc33_contextual_assistant.ps1'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\abc33_contextual_assistant_8093_$Stamp"
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$ExpectedDeltaRelativePaths = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\assets\bf-abc33-assistant-dialog.css',
    '高炉前端数据\assets\bf-abc33-assistant-dialog.js',
    '高炉前端数据\智能助手\backend\assistant_pg.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\abc_score_explanation.py',
    '高炉前端数据\智能助手\backend\abc_rule_assistant_analysis.py',
    '高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql',
    '高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql',
    'tools\service_configs\22012_BFV4PreviewProxy8093.json'
)

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
    param([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 60)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $Desired) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$Name did not reach $Desired within $TimeoutSeconds seconds."
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 90)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening within $TimeoutSeconds seconds."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "8093 stop manager failed with exit code $LASTEXITCODE" }
    Wait-ServiceState -Name $ServiceName -Desired 'Stopped'
    Wait-PortState -Port 8093 -Listening $false
}

function Start-8093 {
    Start-Sleep -Seconds 15
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "8093 start manager failed with exit code $LASTEXITCODE" }
    Wait-ServiceState -Name $ServiceName -Desired 'Running'
    Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 180
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

function Invoke-Migration {
    $PsqlCandidates = @(
        'F:\PostgreSQL\16\bin\psql.exe',
        'C:\Program Files\PostgreSQL\16\bin\psql.exe'
    )
    $Psql = $PsqlCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Psql) { throw 'PostgreSQL 16 psql was not found.' }
    foreach ($Name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        $Value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
        if (-not $Value) { $Value = [Environment]::GetEnvironmentVariable($Name, 'User') }
        if (-not $Value) { throw "Missing required database environment value: $Name" }
        Set-Item -Path "Env:$Name" -Value $Value
    }
    $env:PGPASSWORD = $env:GL02_PGPASSWORD
    & $Psql -X -v ON_ERROR_STOP=1 -h $env:GL02_PGHOST -p $env:GL02_PGPORT -U $env:GL02_PGUSER -d $env:GL02_PGDATABASE -f $MigrationPath
    if ($LASTEXITCODE -ne 0) { throw "ABC contextual assistant migration failed with exit code $LASTEXITCODE" }
}

foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $Python, $DeltaPlanPath, $MigrationPath, $AcceptancePath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
$DeltaPlan = Get-Content -LiteralPath $DeltaPlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ManifestSha256 = (Get-FileHash -LiteralPath $DeltaPlanPath -Algorithm SHA256).Hash
if ($ManifestSha256 -ne $ExpectedManifestSha256.ToUpperInvariant()) {
    throw 'Delta manifest SHA-256 does not match the controller-sealed value.'
}
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
if ($Files.Count -gt $ExpectedDeltaRelativePaths.Count) {
    throw "Delta plan exceeds the $($ExpectedDeltaRelativePaths.Count)-target exact allowlist."
}
$ExpectedTargets = @{}
foreach ($RelativePath in $ExpectedDeltaRelativePaths) {
    $ExpectedTarget = [IO.Path]::GetFullPath((Join-Path $Root $RelativePath))
    $ExpectedStageName = [IO.Path]::GetFileName($RelativePath)
    $ExpectedStage = [IO.Path]::GetFullPath((Join-Path $StageRoot $ExpectedStageName))
    $ExpectedTargets[$ExpectedTarget] = $ExpectedStage
}
$SeenTargets = @{}

foreach ($File in $Files) {
    Assert-BelowRoot -Path $File.Target
    $ResolvedStageRoot = [IO.Path]::GetFullPath($StageRoot).TrimEnd('\') + '\'
    $ResolvedStage = [IO.Path]::GetFullPath($File.Stage)
    if (-not $ResolvedStage.StartsWith($ResolvedStageRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Stage path escapes approved stage root: $($File.Stage)"
    }
    $ResolvedTarget = [IO.Path]::GetFullPath($File.Target)
    if (-not $ExpectedTargets.ContainsKey($ResolvedTarget)) {
        throw "Target is not in the sealed ABC33 exact allowlist: $($File.Target)"
    }
    if ($ResolvedStage -ne $ExpectedTargets[$ResolvedTarget]) {
        throw "Stage/target mapping differs from the sealed ABC33 delta: $($File.Target)"
    }
    if ($SeenTargets.ContainsKey($ResolvedTarget)) { throw "Duplicate target in delta plan: $($File.Target)" }
    $SeenTargets[$ResolvedTarget] = $true
    if (-not (Test-Path -LiteralPath $File.Stage -PathType Leaf)) { throw "Missing staged file: $($File.Stage)" }
    $StageHash = (Get-FileHash -LiteralPath $File.Stage -Algorithm SHA256).Hash
    if ($StageHash -ne $File.DesiredHash) { throw "Staged desired hash mismatch: $($File.Stage)" }
    $Exists = Test-Path -LiteralPath $File.Target -PathType Leaf
    if (-not $Exists -and -not $File.AllowCreate) { throw "Production target missing: $($File.Target)" }
    if ($Exists) {
        $CurrentHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($File.BaselineHashes -notcontains $CurrentHash) { throw "Unreviewed baseline: $($File.Target) $CurrentHash" }
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
$Acceptance = $null
$FilesInstalled = $false
$MigrationApplied = $false

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

    Invoke-Migration
    $MigrationApplied = $true
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
        $FilesInstalled = $true
        $TargetHash = (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash
        if ($TargetHash -ne $File.DesiredHash) { throw "Installed hash mismatch: $($File.Target)" }
        $InstalledHashes[$File.Target] = $TargetHash
    }

    $CompileTargets = @(
        (Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'),
        (Join-Path $Root '高炉前端数据\智能助手\backend\assistant_pg.py'),
        (Join-Path $Root '高炉前端数据\智能助手\backend\abc_rule_assistant_analysis.py'),
        (Join-Path $Root '自动诊断服务\abc_rule_explanation.py')
    )
    & $Python -X utf8 -m py_compile @CompileTargets
    if ($LASTEXITCODE -ne 0) { throw 'Installed Python compilation failed.' }

    Start-8093
    $GuardRestored = $true
    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) { throw '8093 did not start with a new listener PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp#optimization" -TimeoutSec 30
    if ($Page.StatusCode -ne 200) { throw '8093 HTTP verification failed.' }
    foreach ($Marker in @('bf-abc33-assistant-dialog.js', 'abc-furnace-rules-production.js?v=abc33-20260813-a-score-deduction-r2')) {
        if (-not $Page.Content.Contains($Marker)) { throw "8093 page marker missing: $Marker" }
    }
    $Latest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest' -TimeoutSec 30
    if (-not $Latest.ok -or -not $Latest.evaluation_id) { throw '8093 latest ABC API verification failed.' }

    $AcceptanceArguments = @('-NoLogo', '-NoProfile', '-File', $AcceptancePath, '-Port', '8093')
    if ($SkipModelSse) { $AcceptanceArguments += '-SkipModelSse' }
    elseif ($GuestSharedAcceptance) { $AcceptanceArguments += '-GuestShared' }
    else { $AcceptanceArguments += '-SendFollowup' }
    $AcceptanceText = & $Pwsh @AcceptanceArguments | Out-String
    if ($LASTEXITCODE -ne 0) { throw "Production contextual assistant acceptance failed with exit code $LASTEXITCODE" }
    $Acceptance = $AcceptanceText | ConvertFrom-Json
    $ExpectedRequestCount = if ($SkipModelSse) { 0 } elseif ($GuestSharedAcceptance) { 1 } else { 2 }
    if (-not $Acceptance.ok -or [int]$Acceptance.request_count -ne $ExpectedRequestCount) {
        throw 'Production contextual assistant acceptance contract failed.'
    }

    $ProtectedAfter = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }

    [ordered]@{
        ok = $true
        schema = 'bf.abc33.contextual-assistant-production-deploy.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        manifest_sha256 = $ManifestSha256
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $false
        rollback_scope = 'none'
        additive_migration_retained = $MigrationApplied
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        installed_hashes = $InstalledHashes
        delta_plan_sha256 = $ManifestSha256
        artifact_count_delta = $Files.Count
        http_8093 = [int]$Page.StatusCode
        acceptance = $Acceptance
    } | ConvertTo-Json -Depth 9
}
catch {
    $Failure = $_.Exception.Message
    try {
        if (($GuardPaused -or $FilesInstalled) -and (Get-Service -Name $ServiceName).Status -ne 'Stopped') {
            Stop-8093
        }
        if ($FilesInstalled) {
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
            $RollbackApplied = $true
        }
    }
    finally {
        if ($Old8093Pid -and (Get-Service -Name $ServiceName).Status -ne 'Running') {
            Start-8093
            $GuardRestored = $true
        }
        elseif ($Old8093Pid) {
            $GuardRestored = $true
        }
    }
    [ordered]@{
        ok = $false
        schema = 'bf.abc33.contextual-assistant-production-deploy.v1'
        requirement_id = $RequirementId
        execution_id = $ExecutionId
        manifest_sha256 = $ManifestSha256
        failure = $Failure
        backup = $BackupRoot
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        rollback_scope = $(if ($RollbackApplied) { 'application_files_only' } else { 'none' })
        additive_migration_retained = $MigrationApplied
        listener_8093 = Get-ListenerPid -Port 8093
    } | ConvertTo-Json -Depth 6 | Write-Output
    throw $Failure
}
finally {
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
