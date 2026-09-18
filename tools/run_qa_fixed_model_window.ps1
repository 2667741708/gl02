[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Stage,
    [Parameter(Mandatory)][string]$PlanHash,
    [Parameter(Mandatory)][string]$BatchHash,
    [Parameter(Mandatory)][string]$CollectorHash,
    [ValidateRange(15,120)][int]$WindowMinutes = 120
)
$ErrorActionPreference = 'Stop'
throw 'Superseded by REQ-QA-SINGLE-BASE-MODEL-20260917: two-base windows are forbidden; no task or model operation performed.'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Root = 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ExactStage = 'C:/Users/Administrator/AppData/Local/Temp/qa-model-window-v26-20260917-r2'
$TaskPath = '\BlastFurnaceServices\'
$TaskName = 'BFOllamaModelSelectionRecovery'
$Output = Join-Path $Root 'logs/qa_model_window_v26_20260917_r2'
$AuditPath = Join-Path $Output 'window.json'
$Python = 'C:/Program Files/Python311/python.exe'
$Plan = Join-Path $Stage 'templates.remaining.plan.json'
$Batch = Join-Path $Stage 'batch.py'
$Collector = Join-Path $Stage 'collector.py'
if ([IO.Path]::GetFullPath($Stage) -ne [IO.Path]::GetFullPath($ExactStage)) { throw 'Unexpected fixed-window stage' }
foreach ($Binding in @(@($Plan,$PlanHash),@($Batch,$BatchHash),@($Collector,$CollectorHash))) {
    if ((Get-FileHash -LiteralPath $Binding[0] -Algorithm SHA256).Hash -ne $Binding[1]) { throw 'Fixed-window input hash changed' }
}
if (Test-Path -LiteralPath $Output) { throw 'Window output exists; read-only recovery required, no replay' }
$PlanObject = Get-Content -LiteralPath $Plan -Raw | ConvertFrom-Json
$Approved = @('9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb','e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124')
if ($PlanObject.cases.Count -ne 822 -or $PlanObject.model_identity.name -ne 'chiqiongblastfuenace:latest') { throw 'Invalid test cohort or public model' }
if (@($PlanObject.model_identity.approved_digests | Select-Object -Unique).Count -ne 2 -or @($PlanObject.model_identity.approved_digests).Count -ne 2 -or @($PlanObject.model_identity.approved_digests | Where-Object { $_ -notin $Approved }).Count -gt 0) { throw 'Unapproved model pool' }
New-Item -ItemType Directory -Path $Output | Out-Null
if (-not (Test-Path -LiteralPath $Output -PathType Container)) { throw 'Window evidence directory missing' }
$Audit = [ordered]@{ requirement_id='OPS-QA-FIXED-MODEL-WINDOW-20260917'; state='preparing'; task_disabled=$false; task_restored=$false; automatic_replay=$false; window_minutes=$WindowMinutes }
function Save-Audit {
    $Text = $Audit | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($AuditPath, $Text + "`n", $Utf8)
}
function Get-ResidentIdentity {
    $Tags = @( (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6).models | Where-Object { $_.name -eq 'chiqiongblastfuenace:latest' } )
    $Resident = @( (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models )
    if ($Tags.Count -ne 1 -or $Resident.Count -ne 1 -or $Tags[0].digest -notin $Approved -or $Resident[0].digest -ne $Tags[0].digest) { throw 'Approved single resident and alias do not match' }
    return [string]$Tags[0].digest
}
$WindowMutex = [Threading.Mutex]::new($false, 'Global\BFQaFixedModelWindow')
$ModelMutex = [Threading.Mutex]::new($false, 'Global\BFOllamaModelSwitch')
$OwnerTaken = $false
$ModelTaken = $false
$TaskChanged = $false
$WasEnabled = $false
try {
    try { $OwnerTaken = $WindowMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $OwnerTaken = $true }
    if (-not $OwnerTaken) { throw 'Another fixed model window owns this operation' }
    $Task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    $WasEnabled = [bool]$Task.Settings.Enabled
    $Audit.original_task_enabled = $WasEnabled
    Save-Audit
    if ($WasEnabled) {
        # Only future recovery triggers are disabled. A running recovery is allowed to finish.
        $TaskChanged = $true
        Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null
        $Audit.task_disabled = $true
        Save-Audit
    }
    $WaitUntil = [DateTimeOffset]::UtcNow.AddMinutes(10)
    while (-not $ModelTaken -and [DateTimeOffset]::UtcNow -lt $WaitUntil) {
        try { $ModelTaken = $ModelMutex.WaitOne(1000) }
        catch [Threading.AbandonedMutexException] { $ModelTaken = $true }
    }
    if (-not $ModelTaken) { throw 'Running model recovery did not finish within ten minutes; no test sent' }
    $Identity = Get-ResidentIdentity
    Start-Sleep -Seconds 5
    if ((Get-ResidentIdentity) -ne $Identity) { throw 'Model identity is unstable; no test sent' }
    $Deadline = [DateTimeOffset]::UtcNow.AddMinutes($WindowMinutes).ToUnixTimeSeconds()
    # Freeze the one already-resident approved digest for this whole window.
    $PlanObject.model_identity.digest = $Identity
    $PlanObject.model_identity.PSObject.Properties.Remove('approved_digests')
    $ExecutionPlan = Join-Path $Output 'execution.plan.private.json'
    [IO.File]::WriteAllText($ExecutionPlan, ($PlanObject | ConvertTo-Json -Depth 100) + "`n", $Utf8)
    $Audit.state = 'testing'
    $Audit.model_digest = $Identity
    $Audit.source_plan_sha256 = $PlanHash
    $Audit.execution_plan_sha256 = (Get-FileHash -LiteralPath $ExecutionPlan -Algorithm SHA256).Hash.ToLowerInvariant()
    $Audit.deadline_epoch = $Deadline
    Save-Audit
    # No alias switch, warmup, model unload, environment edit, service stop, or other task change.
    & $Python -X utf8 $Batch --root $Root --plan $ExecutionPlan --collector $Collector --output (Join-Path $Output 'batch') --deadline-epoch $Deadline --execute
    if ($LASTEXITCODE -ne 0) { throw 'Bounded test owner failed; inspect claims before any continuation' }
    $Progress = Get-Content -LiteralPath (Join-Path $Output 'batch/progress.json') -Raw | ConvertFrom-Json
    $Audit.state = 'finished'
    $Audit.batch_state = $Progress.state
    $Audit.completed = $Progress.completed
    $Audit.requests = $Progress.requests
} catch {
    $Audit.state = 'blocked'
    $Audit.error_type = $_.Exception.GetType().Name
    throw
} finally {
    try {
        if ($TaskChanged) { Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null }
        if ($OwnerTaken) {
            $Restored = [bool](Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).Settings.Enabled
            $Audit.task_restored = $Restored -eq $WasEnabled
            Save-Audit
            if (-not $Audit.task_restored) { throw 'Recovery task enabled state restoration failed' }
        }
    } finally {
        if ($ModelTaken) { $ModelMutex.ReleaseMutex() }
        if ($OwnerTaken) { $WindowMutex.ReleaseMutex() }
        $ModelMutex.Dispose()
        $WindowMutex.Dispose()
    }
}
