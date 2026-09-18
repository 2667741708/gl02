[CmdletBinding()]
param([Parameter(Mandatory)][string]$Candidate)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
$ExpectedCandidate='1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f'
$ExpectedBaseline='856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa'
$ExpectedCatalog='723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a'
$Manager='F:/Ollama/model-switch/manage_ollama_model_switch.ps1'
$Catalog='F:/Ollama/model-switch/model_catalog.json'
$ExactCandidate='F:/Ollama/model-switch/staging/single-base-20260917-r5/manage_ollama_model_switch.ps1'
$Evidence='F:/Ollama/model-switch/updates/single-base-20260917-r5'
$Backup=Join-Path $Evidence 'manager.before.ps1'
$AtomicBackup=Join-Path $Evidence 'manager.atomic.before.ps1'
$FailedCandidateBackup=Join-Path $Evidence 'manager.failed.candidate.ps1'
$Next=$Manager+'.single-base-r5.next'
$TaskPath='\BlastFurnaceServices\'
$TaskName='BFOllamaModelSelectionRecovery'
if ([IO.Path]::GetFullPath($Candidate) -ne [IO.Path]::GetFullPath($ExactCandidate)) { throw 'Unexpected candidate path' }
if ((Get-FileHash -LiteralPath $Candidate -Algorithm SHA256).Hash -ne $ExpectedCandidate) { throw 'Candidate hash changed' }
$Tokens=$null
$ParseErrors=$null
$CandidateAst=[Management.Automation.Language.Parser]::ParseFile($Candidate,[ref]$Tokens,[ref]$ParseErrors)
if ($ParseErrors.Count) { throw 'Candidate parse failed' }
# The transaction library is transported separately and must match its sealed hash.
$Transaction=Join-Path $PSScriptRoot 'qa_fixed_manager_install_transaction.ps1'
$TransactionHash='7214925ad79e5c4ecd10dc018f0121378769893ea269601df2c47a7e6fa93d91'
if ((Get-FileHash -LiteralPath $Transaction -Algorithm SHA256).Hash -ne $TransactionHash) { throw 'Transaction hash changed' }
. $Transaction
$Mutex=[Threading.Mutex]::new($false,'Global\BFOllamaModelSwitch')
$OperationMutex=[Threading.Mutex]::new($false,'Global\BFQaSingleBaseManagerInstall')
$Taken=$false
$Owner=$false
$Claimed=$false
$Audit=[ordered]@{requirement_id='OPS-QA-SINGLE-BASE-GUARD-INSTALL-20260917';state='preparing';acceptance_scope='manager_source_only';model_operations=0;model_switch_allowed=$false;automatic_replay=$false;identity_ready=$false;production_model_lock_verified=$false;qa_retest_authorized=$false;atomic_replace_completed=$false;rollback_applied=$false}
function Save-InstallAudit {
    [IO.File]::WriteAllText((Join-Path $Evidence 'install.json'),($Audit|ConvertTo-Json -Depth 8)+"`n",$Utf8)
}
function Get-InstallSnapshot {
    $Loaded=@((Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models)
    $Tags=@((Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6).models | Where-Object name -eq 'chiqiongblastfuenace:latest')
    $Processes=@(Get-NetTCPConnection -State Listen | Where-Object LocalPort -in @(8093,8094,8768,8770,5432,11434,8892) | Select-Object LocalPort,OwningProcess | Sort-Object LocalPort,OwningProcess -Unique)
    return [pscustomobject]@{resident=@($Loaded|ForEach-Object {@{name=$_.name;digest=$_.digest}});alias=@($Tags|ForEach-Object {@{name=$_.name;digest=$_.digest}});processes=$Processes}
}
function Invoke-ManagerAtomicReplace {
    param([string]$Source,[string]$Destination,[string]$DestinationBackup)
    if ([string]::IsNullOrWhiteSpace($DestinationBackup)) { throw 'Explicit atomic backup path required' }
    if (Test-Path -LiteralPath $DestinationBackup) { throw 'Atomic backup exists; no overwrite or replay' }
    # PowerShell converts a null string argument into an empty path on this overload.
    [IO.File]::Replace($Source,$Destination,$DestinationBackup)
}
try {
    try { $Owner=$OperationMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $Owner=$true }
    if (-not $Owner) { throw 'Another installer owns the operation' }
    if (Test-Path -LiteralPath $Evidence) { throw 'Operation already claimed; read-only recovery required, no replay' }
    New-Item -ItemType Directory -Path $Evidence | Out-Null
    $Claimed=$true
    Save-InstallAudit
    $Callbacks=@{
        ReadEnabled={ [bool](Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).Settings.Enabled }
        Disable={
            Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null
            if ([bool](Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).Settings.Enabled) { throw 'Recovery task did not disable' }
            $Audit.recovery_disabled=$true
            Save-InstallAudit
        }
        Drain={
            $Until=[DateTimeOffset]::UtcNow.AddMinutes(10)
            while (-not $script:Taken -and [DateTimeOffset]::UtcNow -lt $Until) {
                if ((Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).State -eq 'Running') {
                    Start-Sleep -Seconds 1
                    continue
                }
                try { $script:Taken=$Mutex.WaitOne(0) }
                catch [Threading.AbandonedMutexException] { $script:Taken=$true }
                if (-not $script:Taken) { Start-Sleep -Seconds 1 }
            }
            if (-not $script:Taken) { throw 'Existing model operation did not drain; nothing installed' }
            if ((Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).State -eq 'Running') { throw 'Legacy recovery is still running' }
        }
        Preflight={
            if ((Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash -ne $ExpectedBaseline) { throw 'Manager baseline drift' }
            if ((Get-FileHash -LiteralPath $Catalog -Algorithm SHA256).Hash -ne $ExpectedCatalog) { throw 'Catalog drift' }
            if (Test-Path -LiteralPath $Next) { throw 'Uncertain prior replacement exists' }
            $script:Before=Get-InstallSnapshot
            $Audit.before=$script:Before
            Save-InstallAudit
        }
        Backup={ Copy-Item -LiteralPath $Manager -Destination $Backup }
        Install={
            Copy-Item -LiteralPath $Candidate -Destination $Next
            if ((Get-FileHash -LiteralPath $Next -Algorithm SHA256).Hash -ne $ExpectedCandidate) { throw 'Installation copy changed' }
            Invoke-ManagerAtomicReplace -Source $Next -Destination $Manager -DestinationBackup $AtomicBackup
            $Audit.atomic_replace_completed=$true
        }
        Verify={
            if ((Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash -ne $ExpectedCandidate) { throw 'Installed manager mismatch' }
            if ((Get-FileHash -LiteralPath $Catalog -Algorithm SHA256).Hash -ne $ExpectedCatalog) { throw 'Catalog changed' }
            $After=Get-InstallSnapshot
            if (($Before|ConvertTo-Json -Depth 8 -Compress) -ne ($After|ConvertTo-Json -Depth 8 -Compress)) { throw 'Model identity or protected PID changed during installation' }
            $Audit.after=$After
            $Pin='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
            $Audit.identity_ready=($After.resident.Count -eq 1 -and $After.alias.Count -eq 1 -and
                $After.resident[0].name -ceq 'chiqiongblastfuenace:latest' -and
                $After.alias[0].name -ceq 'chiqiongblastfuenace:latest' -and
                $After.resident[0].digest -ceq $Pin -and $After.alias[0].digest -ceq $Pin)
            $Audit.state='guard_installed'
            $Audit.manager_sha256=$ExpectedCandidate
            Save-InstallAudit
        }
        Rollback={
            $Current=(Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash
            if ($Current -eq $ExpectedCandidate) {
                if ((Get-FileHash -LiteralPath $Backup -Algorithm SHA256).Hash -ne $ExpectedBaseline) { throw 'Rollback backup changed; recovery remains disabled' }
                Copy-Item -LiteralPath $Backup -Destination $Next
                Invoke-ManagerAtomicReplace -Source $Next -Destination $Manager -DestinationBackup $FailedCandidateBackup
                $Audit.rollback_applied=$true
            } elseif ($Current -ne $ExpectedBaseline) { throw 'Unknown manager drift; no overwrite, recovery remains disabled' }
            $Audit.state='failed_recovery_disabled'
            Save-InstallAudit
        }
        Enable={
            # Enable only the verified new manager, never the switching predecessor.
            if ((Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash -ne $ExpectedCandidate) { throw 'Manager changed before task restoration' }
            Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null
        }
        Finish={
            param($Accepted,$OriginalEnabled)
            $Enabled=[bool](Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).Settings.Enabled
            $Audit.original_recovery_enabled=$OriginalEnabled
            $Audit.recovery_enabled=$Enabled
            $Audit.guard_install_accepted=$Accepted
            Save-InstallAudit
            if ($Enabled -ne ($Accepted -and $OriginalEnabled)) { throw 'Recovery task final enabled state mismatch' }
        }
    }
    Invoke-FixedManagerInstallTransaction -Callbacks $Callbacks
} catch {
    if ($Claimed) {
        $Audit.failure_type=$_.Exception.GetType().Name
        if ($Audit.state -eq 'preparing') { $Audit.state='failed_no_acceptance' }
        Save-InstallAudit
    }
    throw
} finally {
    if ($Taken) { $Mutex.ReleaseMutex() }
    if ($Owner) { $OperationMutex.ReleaseMutex() }
    $Mutex.Dispose()
    $OperationMutex.Dispose()
}
