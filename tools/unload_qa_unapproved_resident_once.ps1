[CmdletBinding()]
param([switch]$Execute)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
$Approved='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
$Unapproved='9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
$Name='chiqiongblastfuenace:latest'
$Manager='F:/Ollama/model-switch/manage_ollama_model_switch.ps1'
$Catalog='F:/Ollama/model-switch/model_catalog.json'
$Evidence='F:/Ollama/model-switch/updates/unapproved-resident-unload-20260917-r1'
function Assert-UnapprovedResidentUnloadBoundary {
    param([object]$Tags,[object]$Resident,[string]$ManagerHash,[string]$CatalogHash,[object]$TaskEnabled,[string]$TaskState)
    if ($ManagerHash -cne '1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f' -or
            $CatalogHash -cne '723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a') { throw 'unload_source_identity_invalid' }
    if ($TaskEnabled -isnot [bool] -or $TaskEnabled -or $TaskState -cne 'Disabled') { throw 'unload_recovery_not_drained' }
    foreach ($List in @(@{value=$Tags},@{value=$Resident})) {
        if ($null -eq $List.value -or $List.value -is [string] -or $List.value -is [Collections.IDictionary] -or
                $List.value -isnot [Collections.IEnumerable]) { throw 'unload_model_list_unknown' }
    }
    $Fixed=@($Tags | Where-Object name -CEQ 'chiqiongblastfuenace:1')
    $Public=@($Tags | Where-Object name -CEQ 'chiqiongblastfuenace:latest')
    $Loaded=@($Resident)
    if ($Fixed.Count -ne 1 -or $Fixed[0].digest -cne 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124' -or
            $Public.Count -ne 1 -or $Public[0].digest -cne '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb' -or
            $Loaded.Count -ne 1 -or $Loaded[0].name -cne 'chiqiongblastfuenace:latest' -or
            $Loaded[0].digest -cne '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb') { throw 'unload_observed_identity_invalid' }
}
if (-not $Execute) {
    @{execute=$false;approval_required=$true;action='unload_observed_unapproved_resident_only';approved_digest=$Approved;unapproved_digest=$Unapproved;model_operations=0;weight_files_deleted=0;automatic_replay=$false} | ConvertTo-Json -Compress
    exit 0
}
# Execute is used only by the root task after separate explicit authorization.
$Mutex=[Threading.Mutex]::new($false,'Global\BFOllamaModelSwitch')
$Taken=$false
$Claimed=$false
$Audit=[ordered]@{requirement_id='OPS-QA-RESTORE-FROZEN-BASE-20260917';state='preparing';action='unload_unapproved_resident_only';approved_digest=$Approved;unapproved_digest=$Unapproved;post_started=$false;post_completed=$false;model_operations=0;weight_files_deleted=0;automatic_replay=$false;uncertain_execution=$false}
function Save-UnloadAudit {
    $Text=($Audit | ConvertTo-Json -Depth 8).Replace("`r`n","`n")+"`n"
    [IO.File]::WriteAllText((Join-Path $Evidence 'unload.json'),$Text,$Utf8)
}
function Get-UnloadProcesses {
    return @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -in @(8093,8094,8768,8770,5432,11434,8892) | Select-Object LocalPort,OwningProcess | Sort-Object LocalPort,OwningProcess -Unique)
}
try {
    try { $Taken=$Mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $Taken=$true }
    if (-not $Taken) { throw 'unload_mutex_busy' }
    if (Test-Path -LiteralPath $Evidence) { throw 'unload_already_claimed_readonly_recovery_required' }
    $Task=Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFOllamaModelSelectionRecovery'
    $Tags=(Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6).models
    $Resident=(Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models
    $ManagerHash=(Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash.ToLowerInvariant()
    $CatalogHash=(Get-FileHash -LiteralPath $Catalog -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-UnapprovedResidentUnloadBoundary -Tags $Tags -Resident $Resident -ManagerHash $ManagerHash -CatalogHash $CatalogHash -TaskEnabled $Task.Settings.Enabled -TaskState ([string]$Task.State)
    $BeforeProcesses=@(Get-UnloadProcesses)
    # Recheck metadata after the process probe, immediately before claiming the POST.
    $Tags=(Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6).models
    $Resident=(Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models
    $Task=Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFOllamaModelSelectionRecovery'
    $ManagerHash=(Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash.ToLowerInvariant()
    $CatalogHash=(Get-FileHash -LiteralPath $Catalog -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-UnapprovedResidentUnloadBoundary -Tags $Tags -Resident $Resident -ManagerHash $ManagerHash -CatalogHash $CatalogHash -TaskEnabled $Task.Settings.Enabled -TaskState ([string]$Task.State)
    New-Item -ItemType Directory -Path $Evidence | Out-Null
    $Claimed=$true
    $Audit.before_processes=$BeforeProcesses
    $Audit.state='claimed'
    Save-UnloadAudit
    $Body=@{model=$Name;prompt='';stream=$false;keep_alive=0} | ConvertTo-Json -Compress
    $Audit.post_started=$true
    $Audit.model_operations=1
    $Audit.uncertain_execution=$true
    Save-UnloadAudit
    $Response=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json' -Body $Body -TimeoutSec 30
    if ($Response.done -isnot [bool] -or -not $Response.done -or $Response.done_reason -cne 'unload' -or $Response.model -cne $Name) { throw 'unload_response_invalid' }
    $After=(Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models
    if ($null -eq $After -or $After -is [string] -or $After -is [Collections.IDictionary] -or $After -isnot [Collections.IEnumerable] -or @($After).Count -ne 0) { throw 'unload_not_empty' }
    $AfterProcesses=@(Get-UnloadProcesses)
    if (($BeforeProcesses | ConvertTo-Json -Compress) -cne ($AfterProcesses | ConvertTo-Json -Compress)) { throw 'unload_protected_pid_drift' }
    $Audit.after_processes=$AfterProcesses
    $Audit.post_completed=$true
    $Audit.uncertain_execution=$false
    $Audit.state='unapproved_resident_unloaded_only'
    Save-UnloadAudit
    $Audit | ConvertTo-Json -Depth 8
} catch {
    if ($Claimed) {
        $Audit.failure_type=$_.Exception.GetType().FullName
        $Audit.state='failed_no_replay'
        Save-UnloadAudit
    }
    throw [InvalidOperationException]::new('unapproved_resident_unload_failed_no_replay')
} finally {
    if ($Taken) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
