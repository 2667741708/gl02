[CmdletBinding()]
param(
    [ValidateSet('V3','V4','V5','V6','V7','V8')][string]$Version = 'V3',
    [Parameter(Mandatory)][string]$StageRoot,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$PlanHash,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$GateHash
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Req = 'REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916'
$Service = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools/manage_22012_managed_services.ps1'
$Config = Join-Path $Root 'tools/service_configs/22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$Allowed = @(
    '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
    '高炉前端数据/智能助手/backend/mcp_tool_selection.py',
    '高炉前端数据/智能助手/backend/qa_evidence_policy.py',
    '高炉前端数据/智能助手/backend/qa_task_plan.py',
    '高炉前端数据/智能助手/backend/qa_evidence_claims.py'
)
if ($Version -eq 'V4') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/qa_task_plan.py',
        '高炉前端数据/智能助手/backend/qa_entity_resolution.py',
        '高炉前端数据/智能助手/backend/qa_time_window_plan.py',
        '高炉前端数据/智能助手/backend/qa_report_workflow.py',
        '高炉前端数据/智能助手/mcp/bf_data_mcp_server.py'
    )
}
if ($Version -eq 'V5') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/qa_task_plan.py',
        '高炉前端数据/智能助手/backend/qa_time_window_plan.py',
        '高炉前端数据/智能助手/backend/qa_report_workflow.py',
        '高炉前端数据/智能助手/backend/qa_history_projection.py',
        '高炉前端数据/智能助手/backend/qa_model_readiness.py',
        '高炉前端数据/智能助手/mcp/bf_data_mcp_server.py'
    )
}
$ReleaseName = 'qa-routing-' + $Version.ToLowerInvariant() + '-20260916-r1'
if ($Version -eq 'V6') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/qa_history_projection.py',
        '高炉前端数据/智能助手/backend/mcp_conversation_context.py',
        '高炉前端数据/智能助手/backend/qa_verified_facts.py',
        '高炉前端数据/智能助手/backend/qa_completion.py'
    )
}
$StageRoot = [IO.Path]::GetFullPath($StageRoot)
if ($Version -eq 'V7') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @('高炉前端数据/智能助手/backend/qa_history_projection.py')
}
$ExpectedStage = [IO.Path]::GetFullPath((Join-Path 'C:\Users\Administrator\AppData\Local\Temp' $ReleaseName))
if ($Version -eq 'V8') {
    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $Allowed = @(
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py',
        '高炉前端数据/智能助手/backend/qa_task_plan.py',
        '高炉前端数据/智能助手/backend/qa_document_knowledge.py',
        '高炉前端数据/智能助手/backend/qa_prompt_sources.py'
    )
}
if ($StageRoot -ne $ExpectedStage) { throw 'Stage identity mismatch' }
$PlanPath = Join-Path $StageRoot 'delta-plan.json'
$GatePath = Join-Path $StageRoot 'scope-gate.json'
function Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
if ((Hash $PlanPath) -ne $PlanHash -or (Hash $GatePath) -ne $GateHash) { throw 'Plan/gate bytes changed' }
$Plan = Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json
$Gate = Get-Content -LiteralPath $GatePath -Raw | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne $Req) { throw 'Wrong plan contract' }
if ($Plan.changes.Count -ne $Allowed.Count) { throw 'Exact reviewed target count required' }
if ($Gate.requirement_id -ne $Req -or $Gate.execution_id -ne $ReleaseName) { throw 'Wrong scope gate identity' }
foreach ($Change in $Plan.changes) {
    $Relative = [IO.Path]::GetRelativePath($Root, [string]$Change.target).Replace('\','/')
    if ($Relative -notin $Allowed) { throw 'Target outside exact allowlist' }
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath([string]$Change.stage)) -ne $StageRoot) { throw 'Stage outside exact directory' }
    if ((Hash $Change.stage) -ne $Change.desired_sha256) { throw 'Staged artifact changed' }
    if ($Change.markers) {
        $CandidateText = [IO.File]::ReadAllText([string]$Change.stage, $Utf8)
        foreach ($Marker in @($Change.markers)) {
            if (-not $CandidateText.Contains([string]$Marker)) { throw "Staged marker missing: $Relative" }
        }
    }
}
if (@($Plan.changes.target | Select-Object -Unique).Count -ne $Allowed.Count) { throw 'Duplicate targets' }
function Assert-Baselines {
    foreach ($Change in $Plan.changes) {
        if ($Change.current_exists) {
            if ((Hash $Change.target) -ne $Change.current_sha256) { throw 'Production baseline drift' }
        } elseif (Test-Path -LiteralPath $Change.target) { throw 'Create target appeared' }
    }
    foreach ($Read in $Gate.read_files) {
        if ((Hash (Join-Path $Root $Read.path)) -ne $Read.sha256) { throw 'Dependency drift' }
    }
    $CurrentHead = (& 'C:\Program Files\Git\cmd\git.exe' -C $Root rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Git identity probe failed' }
    if ($CurrentHead -ne $Gate.head) { throw 'Refresh path-scoped preflight before deployment' }
}
function Port-Pid([int]$Port) {
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}
function Protected-Map {
    $Map = [ordered]@{}
    foreach ($Port in @(8094,8768,8770,5432,11434,8892)) { $Map[[string]$Port] = Port-Pid $Port }
    return $Map
}
function Check-Protected($Before) {
    foreach ($Key in $Before.Keys) {
        if ((Port-Pid ([int]$Key)) -ne $Before[$Key]) { throw "Protected listener changed: $Key" }
    }
}
function Wait-Port([bool]$Listening) {
    $Until = (Get-Date).AddSeconds(120)
    do {
        if ([bool](Port-Pid 8093) -eq $Listening) { return }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $Until)
    throw '8093 listener timeout'
}
function Service-Action([string]$Action) {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action $Action -ConfigPath $Config | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Managed service action failed: $Action" }
}
function Install-File([string]$From, [string]$To) {
    $Tmp = "$To.qa-evidence-$([Guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::Copy($From, $Tmp, $false)
    [IO.File]::Move($Tmp, $To, $true)
}
Assert-Baselines
& $Python -m py_compile @($Plan.changes | ForEach-Object { [string]$_.stage })
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 syntax failed' }
$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
$StopAttempted = $false
$Touched = [Collections.Generic.List[object]]::new()
$Backup = Join-Path $Root ('backups/' + $ReleaseName + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$ResultPath = Join-Path $StageRoot 'deployment-result.json'
$Result = [ordered]@{ ok=$false; requirement_id=$Req; backup=$Backup; rollback_applied=$false; guard_paused=$false; guard_restored=$false }
try {
    try { $Acquired = $Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $Acquired=$true }
    if (-not $Acquired) { throw 'Another deployment owns the mutex' }
    Assert-Baselines
    if ((Get-Service -Name $Service).Status -ne 'Running') { throw '8093 not running before change' }
    $Before = Protected-Map
    $OldPid = Port-Pid 8093
    if (-not $OldPid) { throw '8093 has no listener' }
    New-Item -ItemType Directory -Path $Backup | Out-Null
    foreach ($Change in $Plan.changes) {
        if ($Change.current_exists) {
            $Saved = Join-Path $Backup ([IO.Path]::GetFileName($Change.target))
            [IO.File]::Copy($Change.target, $Saved, $false)
            if ((Hash $Saved) -ne $Change.current_sha256) { throw 'Backup verification failed' }
        }
    }
    $StopAttempted=$true
    Service-Action 'stop'
    Wait-Port $false
    $Result.guard_paused=$true
    Check-Protected $Before
    foreach ($Change in $Plan.changes) {
        # Record before replacement so any interrupted install is covered by rollback.
        $Touched.Add($Change)
        Install-File $Change.stage $Change.target
        if ((Hash $Change.target) -ne $Change.desired_sha256) { throw 'Installed hash mismatch' }
    }
    Service-Action 'start'
    Wait-Port $true
    if ((Get-Service -Name $Service).Status -ne 'Running') { throw 'Managed service not restored' }
    $NewPid = Port-Pid 8093
    if ($OldPid -eq $NewPid) { throw 'Expected a new 8093 PID' }
    $Status = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 30
    $Page = Invoke-WebRequest -Uri 'http://127.0.0.1:8093/高炉前端数据/frontend_dashboard_v3.server.html' -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or -not $Status.proxy_ok -or -not $Status.ollama_ok -or -not $Status.model_ok) { throw 'HTTP/model API health failed' }
    Check-Protected $Before
    $Result.ok=$true
    $Result.guard_restored=$true
    $Result.old_8093_pid=$OldPid
    $Result.new_8093_pid=$NewPid
    $Result.protected_before=$Before
    $Result.protected_after=Protected-Map
    $Result.http_8093=200
    $Result.installed_hashes=[ordered]@{}
    foreach ($Change in $Plan.changes) { $Result.installed_hashes[[string]$Change.target] = Hash ([string]$Change.target) }
} catch {
    $Result.failure=$_.Exception.Message
    if ($Acquired -and $Touched.Count -gt 0) {
        Service-Action 'stop'
        Wait-Port $false
        foreach ($Change in $Touched) {
            if ($Change.current_exists) {
                Install-File (Join-Path $Backup ([IO.Path]::GetFileName($Change.target))) $Change.target
                if ((Hash $Change.target) -ne $Change.current_sha256) { throw 'Rollback hash mismatch' }
            } elseif (Test-Path -LiteralPath $Change.target) {
                # Exact allowlisted newly-created file only, no recursive removal.
                Remove-Item -LiteralPath $Change.target
            }
        }
        $Result.rollback_applied=$true
    }
} finally {
    try {
        if ($Acquired -and $StopAttempted) {
            if ((Get-Service -Name $Service).Status -ne 'Running' -or -not (Port-Pid 8093)) {
                Service-Action 'start'
                Wait-Port $true
            }
            $Result.guard_restored=((Get-Service -Name $Service).Status -eq 'Running')
        }
        [IO.File]::WriteAllText($ResultPath, ($Result | ConvertTo-Json -Depth 10), $Utf8)
    } finally {
        if ($Acquired) { $Mutex.ReleaseMutex() }
        $Mutex.Dispose()
    }
}
$Result | ConvertTo-Json -Depth 10
if (-not $Result.ok) { exit 1 }
