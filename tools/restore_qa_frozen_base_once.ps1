[CmdletBinding()]
param([switch]$Execute)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
$Manager='F:/Ollama/model-switch/manage_ollama_model_switch.ps1'
$Catalog='F:/Ollama/model-switch/model_catalog.json'
$Evidence='F:/Ollama/model-switch/updates/frozen-base-contiguous-restore-20260918-r3'
$PriorAudit='F:/Ollama/model-switch/updates/unapproved-resident-unload-20260918-r2/unload.json'
$Approved='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
$Wrong='9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
function Assert-RestoreBoundary {
 param([object]$Tags,[object]$Loaded,[object]$Enabled,[string]$State)
 if ($Enabled -isnot [bool] -or $Enabled -or $State -cnotin @('Disabled','1')) { throw 'restore_task_not_drained' }
 if ($Tags -isnot [array] -or $Loaded -isnot [array]) { throw 'restore_metadata_shape_invalid' }
 $Version=@($Tags | Where-Object name -CEQ 'chiqiongblastfuenace:1')
 $Public=@($Tags | Where-Object name -CEQ 'chiqiongblastfuenace:latest')
 if ($Version.Count -ne 1 -or $Version[0].digest -cne 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124' -or
  $Public.Count -ne 1 -or $Public[0].digest -cne '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb' -or
  $Loaded.Count -ne 1 -or $Loaded[0].name -cne 'chiqiongblastfuenace:latest' -or $Loaded[0].digest -cne $Public[0].digest) { throw 'restore_identity_mismatch' }
}
function Get-RestorePids {
 return @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -in @(8093,8094,8768,8770,5432,11434,8892) | Select-Object LocalPort,OwningProcess | Sort-Object LocalPort,OwningProcess -Unique)
}
function Assert-RestoreSources {
 if ((Get-FileHash -LiteralPath $Manager -Algorithm SHA256).Hash.ToLowerInvariant() -cne '1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f') { throw 'restore_manager_changed' }
 if ((Get-FileHash -LiteralPath $Catalog -Algorithm SHA256).Hash.ToLowerInvariant() -cne '723c4f2c6e5c2093060db8beaf5338dc857477a5b10d5db9f95ec79dfdc2f57a') { throw 'restore_catalog_changed' }
}
function Wait-RestoreEmpty {
 param([scriptblock]$Observe,[scriptblock]$Pause,[int]$MaximumSamples=241)
 for ($Sample=0;$Sample -lt $MaximumSamples;$Sample++) {
  $Models=& $Observe
  if ($null -eq $Models -or $Models -isnot [array]) { throw 'restore_resident_unknown' }
  if ($Models.Count -eq 0) { return }
  if ($Models.Count -ne 1 -or $Models[0].name -cne 'chiqiongblastfuenace:latest' -or $Models[0].digest -cne '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb') { throw 'restore_resident_changed' }
  if ($Sample -lt $MaximumSamples-1) { & $Pause }
 }
 throw 'restore_unload_wait_exhausted_no_replay'
}
if (-not $Execute) {
 @{execute=$false;model_operations=0;automatic_replay=$false;weight_files_deleted=0} | ConvertTo-Json -Compress
 exit 0
}
$Mutex=[Threading.Mutex]::new($false,'Global\BFOllamaModelSwitch')
$Taken=$false
$Claimed=$false
$Audit=[ordered]@{requirement_id='OPS-QA-RESTORE-FROZEN-BASE-20260917';authorization='explicit_user_20260918';state='preparing';automatic_replay=$false;weight_files_deleted=0;unload_posts=0;repair_invocations=0;prior_unload_effect_observed_at='2026-09-18T06:58:07.922771+00:00';prior_unload_replayed=$false}
function Save-RestoreAudit {
 [IO.File]::WriteAllText((Join-Path $Evidence 'restore.json'),($Audit | ConvertTo-Json -Depth 10).Replace("`r`n","`n")+"`n",$Utf8)
}
try {
 $Taken=$Mutex.WaitOne(0)
 if (-not $Taken) { throw 'restore_mutex_busy' }
 if (Test-Path -LiteralPath $Evidence) { throw 'restore_claim_exists_no_replay' }
 Assert-RestoreSources
 $Prior=Get-Content -LiteralPath $PriorAudit -Raw | ConvertFrom-Json
 if ($Prior.state -cne 'failed_no_replay' -or $Prior.post_started -ne $true -or $Prior.model_operations -ne 1 -or $Prior.automatic_replay -ne $false) { throw 'restore_prior_audit_invalid' }
 $Before=@(Get-RestorePids)
 if (($Before | ConvertTo-Json -Compress) -cne ($Prior.before_processes | ConvertTo-Json -Compress)) { throw 'restore_prior_pid_drift' }
 $Task=Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'BFOllamaModelSelectionRecovery'
 $Tags=(Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 6).models
 $Loaded=(Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6).models
 Assert-RestoreBoundary $Tags $Loaded $Task.Settings.Enabled ([string]$Task.State)
 # The prior unload completed (independent empty /api/ps + GIN HTTP 200); this is a new load.
 $Expiry=[datetimeoffset]::Parse([string]$Loaded[0].expires_at)
 if ($Expiry -le [datetimeoffset]::Parse('2026-09-18T06:58:07.922771+00:00')) { throw 'restore_new_load_not_proven' }
 New-Item -ItemType Directory -Path $Evidence | Out-Null
 $Claimed=$true
 $Audit.before_processes=$Before
 $Audit.observed_reloaded_expiry=$Loaded[0].expires_at
 $Audit.state='new_reload_claimed'
 Save-RestoreAudit
 Assert-RestoreSources
 $Audit.unload_posts=1
 $Audit.state='unload_started_no_replay'
 Save-RestoreAudit
 $Body=@{model='chiqiongblastfuenace:latest';prompt='';stream=$false;keep_alive=0} | ConvertTo-Json -Compress
 $Response=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json' -Body $Body -TimeoutSec 30
 $Audit.unload_response=@{done=$Response.done;done_reason=$Response.done_reason;model=$Response.model}
 Save-RestoreAudit
 if ($Response.done -isnot [bool] -or -not $Response.done -or $Response.done_reason -cne 'unload' -or $Response.model -cne 'chiqiongblastfuenace:latest') { throw 'restore_unload_response_invalid' }
 Wait-RestoreEmpty -Observe { $Reply=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 6; return ,$Reply.models } -Pause { Start-Sleep -Milliseconds 250 }
 $Audit.state='new_reload_unloaded'
 $Audit.repair_invocations=1
 Save-RestoreAudit
 # Same PowerShell thread: manager's existing mutex acquisition is recursive, preserving isolation.
 $Text=(& $Manager -Action Repair) -join "`n"
 [IO.File]::WriteAllText((Join-Path $Evidence 'manager-result.json'),$Text+"`n",$Utf8)
 $Result=$Text | ConvertFrom-Json
 if ($Result.ok -ne $true -or $Result.result.identity_ready -ne $true -or $Result.result.assistant_ready -ne $true) { throw 'restore_manager_not_ready' }
 $After=@(Get-RestorePids)
 if (($Before | ConvertTo-Json -Compress) -cne ($After | ConvertTo-Json -Compress)) { throw 'restore_protected_pid_drift' }
 $Audit.after_processes=$After
 $Audit.state='fixed_base_restored'
 $Audit.identity_ready=$true
 $Audit.assistant_ready=$true
 $Audit.alias_changed=$Result.result.alias_changed
 $Audit.warmup=$Result.result.warmup
 Save-RestoreAudit
 $Audit | ConvertTo-Json -Depth 10
} catch {
 if ($Claimed) { $Audit.state='failed_no_replay';$Audit.failure_type=$_.Exception.GetType().FullName;Save-RestoreAudit }
 throw [InvalidOperationException]::new('frozen_base_restore_failed_no_replay')
} finally {
 if ($Taken) { $Mutex.ReleaseMutex() }
 $Mutex.Dispose()
}
