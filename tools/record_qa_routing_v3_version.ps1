[CmdletBinding()]
param([ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10','V11','V12','V13','V14','V15')][string]$Version = 'V3')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This Git record template requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$RequirementId = 'REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916'
$ExecutionId = 'qa-routing-v3-20260916-r1'
$CommitMessage = 'fix: route assistant questions by evidence plan [REQ-QA-ROUTING-ASSISTANT-UPDATE-20260916] [qa-routing-v3-20260916-r1]'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Git = 'C:\Program Files\Git\cmd\git.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$MainRef = 'refs/heads/production-8093'
$StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v3-20260916-r1'
if ($Version -eq 'V4') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v4-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v4-20260916-r1'
    $CommitMessage = 'fix: preserve entities, compare windows and read reports [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v4-20260916-r1]'
}
if ($Version -eq 'V5') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v5-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v5-20260916-r1'
    $CommitMessage = 'fix: bind history owner and adapt real tool results [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v5-20260916-r1]'
}
$Guard = Join-Path $StageRoot 'git_record_guard.py'
if ($Version -eq 'V6') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v6-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v6-20260916-r1'
    $CommitMessage = 'fix: preserve scoped facts and complete assistant answers [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v6-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
}
$OperationPath = Join-Path $StageRoot 'operation.json'
if ($Version -eq 'V7') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v7-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v7-20260916-r1'
    $CommitMessage = 'fix: bind history exclusion SQL patterns [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v7-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
}
$PlanPath = Join-Path $StageRoot 'record-plan.json'
if ($Version -eq 'V8') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v8-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v8-20260916-r1'
    $CommitMessage = 'fix: verify original document scope and preserve permitted prompt evidence [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v8-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V9') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v9-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v9-20260916-r1'
    $CommitMessage = 'fix: resolve original subsections and preserve safe mixed queries [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v9-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V10') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v10-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v10-20260916-r1'
    $CommitMessage = 'fix: resolve unique original atomic clauses and complete table boundaries [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v10-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V11') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v11-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v11-20260916-r1'
    $CommitMessage = 'fix: bound controlled responses to exact owner checked turn messages [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v11-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V12') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v12-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v12-20260916-r1'
    $CommitMessage = 'fix: isolate formal subtasks and preserve readable facts through tool failures [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v12-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V13') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v13-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v13-20260916-r1'
    $CommitMessage = 'fix: render typed current readings in isolated formal compounds [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v13-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V14') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v14-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v14-20260916-r1'
    $CommitMessage = 'fix: bind canonical public units and expose missing-unit completion [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v14-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
if ($Version -eq 'V15') {
    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'
    $ExecutionId = 'qa-routing-v15-20260916-r1'
    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v15-20260916-r1'
    $CommitMessage = 'fix: verify document provenance and complete scoped multi-turn requests [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v15-20260916-r1]'
    $Guard = Join-Path $StageRoot 'git_record_guard.py'
    $OperationPath = Join-Path $StageRoot 'operation.json'
    $PlanPath = Join-Path $StageRoot 'record-plan.json'
}
$Operation = Get-Content -LiteralPath $OperationPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$BaseHead = ([string]$Operation.expected_git_head).ToLowerInvariant()
$ReadSet = @($Operation.git_read_set | ForEach-Object { ([string]$_).Replace('\', '/') })
$Targets = @($Plan.changes | ForEach-Object { ([string]$_.relative).Replace('\', '/') })
$TaskRef = "refs/heads/codex/8093/$ExecutionId"
$VersionRef = "refs/prod-8093/$((Get-Date).ToString('yyyyMMdd'))/$ExecutionId"
$ZeroOid = '0000000000000000000000000000000000000000'
$MaximumCasAttempts = 3
$OriginalIndex = $env:GIT_INDEX_FILE

function Run-Git {
    param([string[]]$Arguments)
    $Result = & $Git -c core.quotepath=false -C $Root @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Git command failed: $($Arguments -join ' '): $($Result -join ' ')" }
    return @($Result)
}

function Get-GitText {
    param([string[]]$Arguments)
    return ((Run-Git -Arguments $Arguments) -join "`n").Trim()
}

function Write-Utf8Json {
    param([string]$Path, [object]$Value)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), $Utf8NoBom)
}

function Get-AcceptedTargetStates {
    $States = [ordered]@{}
    foreach ($Change in @($Plan.changes)) {
        $Relative = ([string]$Change.relative).Replace('\', '/')
        $Installed = (Get-FileHash -LiteralPath ([string]$Change.target) -Algorithm SHA256).Hash
        $Desired = ([string]$Change.desired_sha256).ToUpperInvariant()
        if ($Installed -ne $Desired) { throw "Accepted installed hash drifted: $Relative" }
        $States[$Relative] = [ordered]@{ sha256 = $Installed }
    }
    return $States
}

function Sync-RealIndexTargets {
    param([string[]]$Paths)
    $SavedIndex = $env:GIT_INDEX_FILE
    if ($null -ne $SavedIndex) { Remove-Item Env:GIT_INDEX_FILE }
    try {
        for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
            & $Git -c core.quotepath=false -C $Root reset -q HEAD -- @Paths 2>$null
            if ($LASTEXITCODE -eq 0) { return }
            if ($Attempt -lt 3) { Start-Sleep -Milliseconds (100 * $Attempt) }
        }
        throw 'Could not synchronize accepted target entries in the real index.'
    }
    finally {
        if ($null -ne $SavedIndex) { $env:GIT_INDEX_FILE = $SavedIndex }
    }
}

foreach ($Required in @($Root, $Git, $Python, $Guard, $OperationPath, $PlanPath)) {
    if (-not (Test-Path -LiteralPath $Required)) { throw "Missing concurrent Git record input: $Required" }
}
if (($RequirementId + $ExecutionId + $CommitMessage + $StageRoot).Contains('__')) { throw 'Unresolved template placeholder.' }
if ($ExecutionId -notmatch '^[A-Za-z0-9._-]+$') { throw 'ExecutionId is not safe for a Git ref.' }
if ($Operation.requirement_id -ne $RequirementId -or $Plan.requirement_id -ne $RequirementId) { throw 'Git record identity mismatch.' }
if ($Targets.Count -eq 0) { throw 'Concurrent Git record requires at least one accepted target.' }
if ($Targets.Count -ne @($Targets | Sort-Object -Unique).Count) { throw 'Concurrent Git record target list contains duplicates.' }
if (& $Git -C $Root rev-parse --verify --quiet $TaskRef 2>$null) { throw 'Task branch ref already exists.' }
if (& $Git -C $Root rev-parse --verify --quiet $VersionRef 2>$null) { throw 'Production version ref already exists.' }

$Acceptance = Get-Content -LiteralPath (Join-Path $StageRoot 'deployment-result.json') -Raw | ConvertFrom-Json
if (-not $Acceptance.ok -or -not $Acceptance.guard_restored -or $Acceptance.rollback_applied) { throw 'No accepted deployment' }
$AcceptedTargets = Get-AcceptedTargetStates
$IntegratedCommit = $null
$IntegratedParent = $null
$IntegrationState = $null
$StagedGate = $null
$CasAttempts = 0

try {
    for ($Attempt = 1; $Attempt -le $MaximumCasAttempts; $Attempt++) {
        $CasAttempts = $Attempt
        $CurrentTip = (Get-GitText -Arguments @('rev-parse', '--verify', $MainRef)).ToLowerInvariant()
        $IntegrationExpectation = [ordered]@{
            schema = 'bf.deploy.concurrent-integration-expectation.v1'
            repo = $Root
            base_head = $BaseHead
            main_ref = $MainRef
            write_set = $Targets
            read_set = $ReadSet
        }
        $IntegrationPath = Join-Path $StageRoot "integration-$Attempt.json"
        Write-Utf8Json -Path $IntegrationPath -Value $IntegrationExpectation
        $IntegrationText = (& $Python -X utf8 $Guard classify-integration --expectation $IntegrationPath) -join "`n"
        if ($LASTEXITCODE -ne 0) { throw "Concurrent integration rejected: $IntegrationText" }
        $IntegrationState = $IntegrationText | ConvertFrom-Json
        if (-not $IntegrationState.ok -or $IntegrationState.action -ne 'integrate_on_current_tip') {
            throw "Concurrent integration conflict: $($IntegrationState.conflict_paths -join ', ')"
        }
        if ([string]$IntegrationState.current_tip -ne $CurrentTip) { continue }

        $AcceptedTargets = Get-AcceptedTargetStates
        $IsolatedIndex = Join-Path $StageRoot "isolated-index-$Attempt"
        $env:GIT_INDEX_FILE = $IsolatedIndex
        Run-Git -Arguments @('read-tree', $CurrentTip) | Out-Null
        Run-Git -Arguments (@('add', '--') + $Targets) | Out-Null
        $RecordExpectation = [ordered]@{
            schema = 'bf.deploy.git-record-expectation.v1'
            repo = $Root
            expected_head = $CurrentTip
            version_ref = $VersionRef
            targets = $AcceptedTargets
        }
        $RecordExpectationPath = Join-Path $StageRoot "record-$Attempt.json"
        Write-Utf8Json -Path $RecordExpectationPath -Value $RecordExpectation
        $GateText = (& $Python -X utf8 $Guard check-staged --expectation $RecordExpectationPath) -join "`n"
        if ($LASTEXITCODE -ne 0) { throw "Isolated staged gate failed: $GateText" }
        $StagedGate = $GateText | ConvertFrom-Json
        $Tree = Get-GitText -Arguments @('write-tree')
        $CandidateCommit = Get-GitText -Arguments @('commit-tree', $Tree, '-p', $CurrentTip, '-m', $CommitMessage)

        Remove-Item Env:GIT_INDEX_FILE
        & $Git -C $Root update-ref $MainRef $CandidateCommit $CurrentTip 2>$null
        if ($LASTEXITCODE -eq 0) {
            $IntegratedCommit = $CandidateCommit
            $IntegratedParent = $CurrentTip
            break
        }
    }
}
finally {
    if ($null -eq $OriginalIndex) {
        Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
    }
    else {
        $env:GIT_INDEX_FILE = $OriginalIndex
    }
}

if (-not $IntegratedCommit) { throw "Mainline CAS did not succeed after $MaximumCasAttempts attempts." }
& $Git -C $Root update-ref $TaskRef $IntegratedCommit $ZeroOid
if ($LASTEXITCODE -ne 0) { throw 'Task branch ref creation failed after mainline integration.' }
& $Git -C $Root update-ref $VersionRef $IntegratedCommit $ZeroOid
if ($LASTEXITCODE -ne 0) { throw 'Immutable production version ref creation failed after mainline integration.' }
Sync-RealIndexTargets -Paths $Targets

$Head = (Get-GitText -Arguments @('rev-parse', '--verify', $MainRef)).ToLowerInvariant()
if ($Head -ne $IntegratedCommit) { throw 'Mainline moved again before post-record evidence was captured.' }
$Remaining = @(& $Git -c core.quotepath=false -C $Root status --porcelain=v1 -- @Targets) | Where-Object { $_ }
if ($Remaining.Count) { throw "Accepted target paths are not clean after index synchronization: $($Remaining -join ', ')" }

$RecordResult = [ordered]@{
    ok = $true
    schema = 'bf.deploy.concurrent-git-record.v1'
    requirement_id = $RequirementId
    execution_id = $ExecutionId
    base_head = $BaseHead
    integrated_parent = $IntegratedParent
    production_git_commit = $IntegratedCommit
    production_git_branch = $MainRef
    task_branch_ref = $TaskRef
    production_version_ref = $VersionRef
    write_set = $Targets
    read_set = $ReadSet
    cas_attempts = $CasAttempts
    real_index_scope = $Targets
    unrelated_index_entries_preserved = $true
    integration_state = $IntegrationState
    staged_guard = $StagedGate
}
Write-Utf8Json -Path (Join-Path $StageRoot 'git-record-result.json') -Value $RecordResult
$RecordResult | ConvertTo-Json -Depth 12
