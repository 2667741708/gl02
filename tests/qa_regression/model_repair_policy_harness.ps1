[CmdletBinding()]
param([Parameter(Mandatory)][string]$PolicyFile,[Parameter(Mandatory)][string]$RepairFile,
      [Parameter(Mandatory)][string]$Workdir,[Parameter(Mandatory)][string]$Mode,
      [string]$ActualDependency,[string]$SwitchFile)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
Set-StrictMode -Version Latest
$script:Catalog=[pscustomobject]@{state_path=(Join-Path $Workdir 'state.json');public_alias='synthetic:latest';fallback_order=@('m1','m0')}
$script:Models=@([pscustomobject]@{id='m0';version_tag='synthetic:0';preferred_digest='digest0';context_length=32768},[pscustomobject]@{id='m1';version_tag='synthetic:1';preferred_digest='digest1';context_length=32768})
$global:Alias='digest0'
$global:Resident=$Mode -in @('healthy','healthy_status_error','switch_pause_partial_error','switch_stale_activation_error')
$global:HealthEnabled=$Mode -ne 'original_health_disabled'
$global:Calls=[Collections.Generic.List[string]]::new()
$global:State=[pscustomobject]@{desired_model_id='m1';effective_model_id='m1';digest='digest1'}
$global:SwitchingSucceeded=$false
function Ensure-OllamaService { $global:Calls.Add('ensure_service') }
function Initialize-State { return $global:State }
function Read-State { return $global:State }
function Get-PublicTag { return [pscustomobject]@{name='synthetic:latest';digest=$global:Alias} }
function Find-ModelByDigest { param($Digest) return $script:Models | Where-Object preferred_digest -eq $Digest }
function Get-ModelDefinition { param($Id) return $script:Models | Where-Object id -eq $Id }
function Test-ModelTag { param($Model) return [pscustomobject]@{digest=$Model.preferred_digest} }
function Test-PublicAliasResident { param($ExpectedDigest) return $global:Resident -and $global:Alias -eq $ExpectedDigest }
function Get-HealthTaskEnabled { return $global:HealthEnabled }
function Set-HealthTaskPaused {
    param($Paused)
    $global:Calls.Add('health_pause_'+$Paused)
    $global:HealthEnabled=-not $Paused
    if ($Mode -in @('pause_partial_error','switch_pause_partial_error') -and $Paused) { throw 'synthetic pause failure after mutation' }
}
function Write-Event { param($Level,$Event,$Data) $global:Calls.Add('event_'+$Event) }
function Write-JsonFileAtomic {
    param($Path,$Value)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 12), $Utf8)
    if ($Path -eq $script:Catalog.state_path) { $global:State=$Value }
}
function Invoke-Ollama {
    param($Arguments)
    if ($Arguments.Count -ne 3 -or $Arguments[0] -ne 'cp' -or $Arguments[2] -ne 'synthetic:latest') { throw 'Unexpected model mutation' }
    $global:Calls.Add('rollback_'+$Arguments[1])
    if ($Mode -eq 'rollback_error' -and $Arguments[1] -eq 'synthetic:0' -and $global:Alias -ne 'digest0') { throw 'synthetic alias rollback failure' }
    $model=@($script:Models | Where-Object version_tag -eq $Arguments[1])
    if ($model.Count -ne 1) { throw 'Unknown rollback version' }
    $global:Alias=$model[0].preferred_digest
}
function Activate-Model {
    param($Model,$DesiredModelId,$ActionName,$FallbackActive)
    $global:Calls.Add('activate_'+$Model.id+'_'+$ActionName)
    if ($Mode -eq 'healthy_status_error') { throw 'synthetic secondary status endpoint unavailable' }
    if ($global:Alias -ne $Model.preferred_digest) {
        $global:Calls.Add('alias_'+$Model.id)
        $global:Alias=$Model.preferred_digest
    }
    if ($ActionName -ne 'RepairResident') {
        $global:Calls.Add('warmup_'+$Model.id)
        if ($Mode -in @('all_fail','rollback_error') -or ($Mode -in @('fallback_success','switch_stale_activation_error') -and $Model.id -eq 'm1')) { throw 'synthetic warmup network failure' }
        $global:Resident=$true
    }
    $global:State=[pscustomobject]@{desired_model_id=$DesiredModelId;effective_model_id=$Model.id;digest=$Model.preferred_digest;fallback_active=$FallbackActive}
    Write-JsonFileAtomic -Path $script:Catalog.state_path -Value $global:State
    $global:SwitchingSucceeded=$true
    return [pscustomobject]@{state=$global:State;alias_changed=$false}
}
. $PolicyFile
. $RepairFile
if ($ActualDependency) {
    function Ensure-ModelTag { param($Model) return [pscustomobject]@{digest=$Model.preferred_digest} }
    function Get-UtcTimestamp { return [DateTimeOffset]::UtcNow.ToString('o') }
    function Invoke-RestMethod {
        param($Method,$Uri,$TimeoutSec)
        if ($Method -ne 'Get' -or $Uri -ne 'synthetic-api/api/ps') { throw 'Unexpected real-dependency HTTP request' }
        $Loaded=@()
        if ($global:Resident) { $Loaded=@([pscustomobject]@{name='synthetic:latest';digest=$global:Alias}) }
        return [pscustomobject]@{models=$Loaded}
    }
    function Invoke-Warmup {
        $Model=Find-ModelByDigest $global:Alias
        $global:Calls.Add('warmup_'+$Model.id)
        if ($Mode -in @('all_fail','rollback_error') -or ($Mode -in @('fallback_success','switch_stale_activation_error') -and $Model.id -eq 'm1')) { throw 'synthetic warmup network failure' }
        $global:Resident=$true
        return [pscustomobject]@{skipped=$false}
    }
    function Test-StatusEndpoints {
        if ($Mode -eq 'healthy_status_error') { throw 'synthetic secondary status endpoint unavailable' }
        return @([pscustomobject]@{ok=$true})
    }
    $script:Catalog | Add-Member -NotePropertyName api_base -NotePropertyValue 'synthetic-api'
    $SkipWarmup=$false
    . $ActualDependency
    if ($SwitchFile) { . $SwitchFile }
}
if ($Mode -eq 'policy_backoff') {
    $Policy=@{schema_version=1;failures=@{}}
    $Now=[DateTimeOffset]::Parse('2026-01-01T00:00:00+00:00')
    $Seconds=@()
    foreach ($Attempt in 1..8) {
        $Policy.failures.m1=New-RepairCandidateFailure -Policy $Policy -CandidateId 'm1' -Now $Now
        $Seconds+=$Policy.failures.m1.cooldown_seconds
    }
    @{seconds=$Seconds; cooling_before=(Test-RepairCandidateCooling -Policy $Policy -CandidateId 'm1' -Now $Now.AddSeconds(899)); cooling_at=(Test-RepairCandidateCooling -Policy $Policy -CandidateId 'm1' -Now $Now.AddSeconds(900))} | ConvertTo-Json
    exit 0
}
if ($Mode -in @('policy_bad_count','policy_bad_time')) {
    $Policy=@{schema_version=1;failures=@{m1=@{attempts='invalid';retry_after='invalid'}}}
    $Rejected=$false
    try {
        if ($Mode -eq 'policy_bad_count') { $Value=New-RepairCandidateFailure -Policy $Policy -CandidateId 'm1' -Now ([DateTimeOffset]::UtcNow) }
        else { $Value=Test-RepairCandidateCooling -Policy $Policy -CandidateId 'm1' -Now ([DateTimeOffset]::UtcNow) }
    } catch { $Rejected=$true }
    @{rejected=$Rejected} | ConvertTo-Json
    exit 0
}
if ($Mode -in @('cooldown_all','cooldown_preferred')) {
    $Failures=@{m1=@{attempts=[long]1;retry_after=[DateTimeOffset]::UtcNow.AddHours(1).ToString('o')}}
    if ($Mode -eq 'cooldown_all') { $Failures.m0=@{attempts=[long]1;retry_after=[DateTimeOffset]::UtcNow.AddHours(1).ToString('o')} }
    Write-JsonFileAtomic -Path (Get-RepairPolicyPath) -Value @{schema_version=1;failures=$Failures}
}
if ($Mode -eq 'invalid_policy') {
    [IO.File]::WriteAllText((Get-RepairPolicyPath),'{"schema_version":1,"failures":"invalid"}', $Utf8)
}
$Failed=$false
$Message=''
try {
    if ($Mode.StartsWith('switch_')) { $ModelId='m1'; $Result=Invoke-Switch }
    else { $Result=Invoke-Repair }
}
catch { $Failed=$true; $Message=$_.Exception.Message }
@{failed=$Failed;message=$Message;alias=$global:Alias;resident=$global:Resident;health_enabled=$global:HealthEnabled;
  activation_success=$global:SwitchingSucceeded;state=$global:State;calls=@($global:Calls.ToArray())} | ConvertTo-Json -Depth 12
