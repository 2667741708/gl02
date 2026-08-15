[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedPlanSha256,
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_http400_20260814'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
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
$PlanPath = Join-Path $StageRoot 'delta-plan.json'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)
$Allowed = [ordered]@{
    '高炉前端数据\assets\bf-abc33-assistant-dialog.js' = 'bf-abc33-assistant-dialog.js'
    '高炉前端数据\frontend_dashboard_v3.server.html' = 'frontend_dashboard_v3.server.html'
}

function Get-ListenerPid([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedMap {
    $Result = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Result[[string]$Port] = Get-ListenerPid $Port }
    return $Result
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 90) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening."
}

function Invoke-ServiceAction([string]$Action) {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action $Action -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Service action $Action failed with exit code $LASTEXITCODE." }
}

foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $PlanPath)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing required input: $Required" }
}
$ActualPlanSha256 = (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash
if ($ActualPlanSha256 -ne $ExpectedPlanSha256.ToUpperInvariant()) { throw 'Delta plan SHA-256 mismatch.' }
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne 'BUG-ABC33-QA-HTTP400-20260814') {
    throw 'Delta plan identity mismatch.'
}
$Changes = @($Plan.changes)
if ($Changes.Count -ne 2) { throw 'This deployment requires exactly two artifacts.' }
$Validated = @()
$Seen = @{}
foreach ($Change in $Changes) {
    $Relative = [string]$Change.target_relative
    if (-not $Allowed.Contains($Relative) -or $Seen.ContainsKey($Relative)) { throw "Unapproved target: $Relative" }
    $Seen[$Relative] = $true
    $Stage = Join-Path $StageRoot $Allowed[$Relative]
    $Target = Join-Path $Root $Relative
    if (-not (Test-Path -LiteralPath $Stage -PathType Leaf)) { throw "Missing staged artifact: $Stage" }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Missing production target: $Target" }
    $Desired = ([string]$Change.desired_sha256).ToUpperInvariant()
    $Baseline = @($Change.baseline_sha256 | ForEach-Object { ([string]$_).ToUpperInvariant() })
    if ((Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash -ne $Desired) { throw "Staged hash mismatch: $Relative" }
    $Current = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    if ($Baseline -notcontains $Current) { throw "Production baseline drift: $Relative $Current" }
    $Text = Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
    foreach ($Marker in @($Change.markers)) {
        if (-not $Text.Contains([string]$Marker)) { throw "Artifact marker missing: $Relative" }
    }
    $Validated += [pscustomobject]@{ Relative = $Relative; Stage = $Stage; Target = $Target; Desired = $Desired }
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
$Stopped = $false
$Installed = $false
$Rollback = $false
$OldPid = $null
$NewPid = $null
$ProtectedBefore = $null
$BackupRoot = Join-Path $Root ('backups\abc33_http400_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
try {
    $Acquired = $Mutex.WaitOne(0)
    if (-not $Acquired) { throw 'Another 8093 deployment owns the mutex.' }
    if ((Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') { throw '8093 guard is not running.' }
    $OldPid = Get-ListenerPid 8093
    if (-not $OldPid) { throw '8093 is not listening.' }
    $ProtectedBefore = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening." }
    }
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($Item in $Validated) {
        $Backup = Join-Path $BackupRoot $Item.Relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
        Copy-Item -LiteralPath $Item.Target -Destination $Backup -Force
    }

    Invoke-ServiceAction 'stop'
    $Stopped = $true
    Wait-Port 8093 $false
    foreach ($Key in $ProtectedBefore.Keys) {
        if ((Get-ListenerPid ([int]$Key)) -ne $ProtectedBefore[$Key]) { throw "Protected port $Key changed during stop." }
    }
    $Installed = $true
    foreach ($Item in $Validated) {
        $Temporary = "$($Item.Target).deploying-$ExecutionId"
        Copy-Item -LiteralPath $Item.Stage -Destination $Temporary -Force
        Move-Item -LiteralPath $Temporary -Destination $Item.Target -Force
        if ((Get-FileHash -LiteralPath $Item.Target -Algorithm SHA256).Hash -ne $Item.Desired) {
            throw "Installed hash mismatch: $($Item.Relative)"
        }
    }
    Invoke-ServiceAction 'start'
    $Stopped = $false
    Wait-Port 8093 $true 180
    $NewPid = Get-ListenerPid 8093
    if (-not $NewPid -or $NewPid -eq $OldPid) { throw '8093 did not start with a new PID.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$ExecutionId#optimization" -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains('abc33-initial-question-20260814-r1')) {
        throw 'Production HTML cache marker verification failed.'
    }
    $Asset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf-abc33-assistant-dialog.js?v=$ExecutionId" -TimeoutSec 30
    $GoodQuestion = '请解释当前炉况规则的判断依据、形成过程与处置顺序。'
    $BadQuestion = '请基于当前ABC33规则上下文，解释本次评分依据、关键计算项、物理语义和五步处置顺序。'
    if ($Asset.StatusCode -ne 200 -or -not $Asset.Content.Contains($GoodQuestion) -or $Asset.Content.Contains($BadQuestion)) {
        throw 'Production assistant question contract verification failed.'
    }
    $Latest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest' -TimeoutSec 30
    if (-not $Latest.ok) { throw 'ABC33 latest API verification failed.' }
    $ProtectedAfter = Get-ProtectedMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed: $Key" }
    }
    [ordered]@{
        ok = $true
        schema = 'bf.deploy.abc33-initial-question.v1'
        execution_id = $ExecutionId
        plan_sha256 = $ActualPlanSha256
        backup = $BackupRoot
        old_8093_pid = $OldPid
        new_8093_pid = $NewPid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        http_8093 = [int]$Page.StatusCode
        artifact_count = $Validated.Count
    } | ConvertTo-Json -Depth 6
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ($Installed) {
            if (-not $Stopped) {
                Invoke-ServiceAction 'stop'
                Wait-Port 8093 $false
                $Stopped = $true
            }
            foreach ($Item in $Validated) {
                $Backup = Join-Path $BackupRoot $Item.Relative
                if (Test-Path -LiteralPath $Backup -PathType Leaf) {
                    Copy-Item -LiteralPath $Backup -Destination $Item.Target -Force
                }
            }
            $Rollback = $true
        }
    }
    finally {
        if ($Stopped) {
            Invoke-ServiceAction 'start'
            Wait-Port 8093 $true 180
            $Stopped = $false
        }
    }
    [ordered]@{
        ok = $false
        schema = 'bf.deploy.abc33-initial-question.v1'
        execution_id = $ExecutionId
        failure = $Failure
        backup = $BackupRoot
        rollback_applied = $Rollback
        listener_8093 = Get-ListenerPid 8093
    } | ConvertTo-Json -Depth 5 | Write-Output
    throw $Failure
}
finally {
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
