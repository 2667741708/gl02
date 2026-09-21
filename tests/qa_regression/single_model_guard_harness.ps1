[CmdletBinding()]
param([Parameter(Mandatory)][string]$GuardFile,[Parameter(Mandatory)][string]$Workdir,
      [Parameter(Mandatory)][string]$Mode)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
Set-StrictMode -Version Latest
$script:FixturePinDigest='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
$script:FixtureOtherDigest='9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb'
$script:Catalog=[pscustomobject]@{public_alias='chiqiongblastfuenace:latest';api_base='synthetic-api';state_path=(Join-Path $Workdir 'state.json');
 status_endpoints=@('http://127.0.0.1:8093/api/ollama/status','http://127.0.0.1:8094/api/ollama/status');
 models=@([pscustomobject]@{id='fixed';version_tag='chiqiongblastfuenace:1';preferred_digest=$script:FixturePinDigest;context_length=32768},
          [pscustomobject]@{id='other';version_tag='synthetic:other';preferred_digest=$script:FixtureOtherDigest;context_length=32768})}
$global:Alias=$script:FixturePinDigest
$global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixturePinDigest})
$global:Calls=[Collections.Generic.List[string]]::new()
$global:Events=[Collections.Generic.List[object]]::new()
$global:ResidentReads=0
$global:StatusReads=0
$global:LogWrites=0
$global:StateWrites=0
$global:AliasReads=0
$global:InstalledReads=0
$global:FixtureSecret='fixture-password-private-user-token'
if ($Mode -in @('alias_repair','cp_error','alias_recheck_error')) { $global:Alias=$script:FixtureOtherDigest }
if ($Mode -in @('empty_resident','initialize_empty','logger_pipeline_stop','warmup_error','warmup_cancel','warmup_no_resident','warmup_alias_drift','warmup_wrong_resident')) { $global:Loaded=@() }
if ($Mode -eq 'empty_and_wrong_alias') { $global:Loaded=@();$global:Alias=$script:FixtureOtherDigest }
if ($Mode -in @('wrong_resident','initialize_wrong')) { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixtureOtherDigest}) }
if ($Mode -eq 'resident_digest_sensitive') { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$global:FixtureSecret}) }
if ($Mode -eq 'wrong_resident_name') { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:1';digest=$script:FixturePinDigest}) }
if ($Mode -eq 'missing_resident_digest') { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest'}) }
if ($Mode -in @('multiple_residents','initialize_multiple')) { $global:Loaded+=@([pscustomobject]@{name='synthetic:other';digest=$script:FixtureOtherDigest}) }
if ($Mode -eq 'bad_catalog') { $script:Catalog.models[0].preferred_digest=$script:FixtureOtherDigest }
if ($Mode -eq 'bad_catalog_tag') { $script:Catalog.models[0].version_tag='synthetic:other' }
if ($Mode -eq 'bad_catalog_alias') { $script:Catalog.public_alias='synthetic:other' }
if ($Mode -eq 'duplicate_catalog') { $script:Catalog.models+=@($script:Catalog.models[0]) }
if ($Mode -eq 'missing_status_endpoint') { $script:Catalog.status_endpoints=@('http://127.0.0.1:8093/api/ollama/status') }
function Get-PublicTag {
    $global:AliasReads++
    if ($Mode -eq 'alias_api_error') { throw [InvalidOperationException]::new($global:FixtureSecret) }
    if ($Mode -eq 'alias_after_api_error' -and $global:AliasReads -gt 2) { throw [InvalidOperationException]::new($global:FixtureSecret) }
    if ($Mode -eq 'alias_unknown') { return [pscustomobject]@{name='chiqiongblastfuenace:latest'} }
    return [pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$global:Alias}
}
function Test-ModelTag {
    param($Model)
    $global:InstalledReads++
    if ($Mode -eq 'missing_fixed') { return $null }
    if ($Mode -eq 'installed_api_error') { throw [InvalidOperationException]::new($global:FixtureSecret) }
    if ($Mode -eq 'installed_after_api_error' -and $global:InstalledReads -gt 1) { throw [InvalidOperationException]::new($global:FixtureSecret) }
    if ($Mode -eq 'installed_wrong_digest') { return [pscustomobject]@{digest=$script:FixtureOtherDigest} }
    return [pscustomobject]@{digest=$Model.preferred_digest}
}
function Get-UtcTimestamp { return '2026-09-17T00:00:00Z' }
function Write-JsonFileAtomic {
    param($Path,$Value)
    $global:StateWrites++
    if ($Mode -in @('state_error','state_error_log_error','state_error_log_cancel')) { throw [IO.IOException]::new($global:FixtureSecret) }
    if ($Mode -eq 'state_final_error' -and $global:StateWrites -eq 2) { throw [IO.IOException]::new($global:FixtureSecret) }
    [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 12),$Utf8)
}
function Write-Event {
    param($Level,$Event,$Data)
    $global:LogWrites++
    if ($Mode -in @('log_error','state_error_log_error')) { throw [IO.IOException]::new($global:FixtureSecret) }
    if ($Mode -eq 'logger_cancel') { throw [OperationCanceledException]::new($global:FixtureSecret) }
    if ($Mode -eq 'logger_pipeline_stop') {
        [IO.File]::WriteAllText((Join-Path $Workdir 'pipeline-stop-observed.txt'),'synthetic pipeline cancellation',$Utf8)
        throw [Management.Automation.PipelineStoppedException]::new($global:FixtureSecret)
    }
    if ($Mode -eq 'state_error_log_cancel' -and $Data.outcome -eq 'failed') { throw [OperationCanceledException]::new($global:FixtureSecret) }
    if ($Mode -eq 'state_started_log_error' -and $Data.stage -eq 'state-write' -and $Data.outcome -eq 'started') { throw [IO.IOException]::new($global:FixtureSecret) }
    if ($Mode -eq 'state_passed_log_error' -and $Data.stage -eq 'state-write' -and $Data.outcome -eq 'pending') { throw [IO.IOException]::new($global:FixtureSecret) }
    if ($Mode -eq 'state_passed_log_cancel' -and $Data.stage -eq 'state-write' -and $Data.outcome -eq 'pending') { throw [OperationCanceledException]::new($global:FixtureSecret) }
    if ($Mode -eq 'state_passed_pipeline_stop' -and $Data.stage -eq 'state-write' -and $Data.outcome -eq 'pending') {
        [IO.File]::WriteAllText((Join-Path $Workdir 'pipeline-stop-observed.txt'),'synthetic pipeline cancellation',$Utf8)
        throw [Management.Automation.PipelineStoppedException]::new($global:FixtureSecret)
    }
    $global:Events.Add([pscustomobject]@{level=$Level;event=$Event;data=$Data})
}
function Invoke-RestMethod {
    param($Method,$Uri,$TimeoutSec)
    if ($Method -ne 'Get') { throw 'Unexpected network operation' }
    if ($Uri -eq 'synthetic-api/api/ps') {
        $global:ResidentReads++
        if ($Mode -eq 'resident_null') { return [pscustomobject]@{models=$null} }
        if ($Mode -eq 'resident_missing') { return [pscustomobject]@{} }
        if ($Mode -eq 'resident_string') { return [pscustomobject]@{models='unknown'} }
        if ($Mode -eq 'resident_single_object') { return [pscustomobject]@{models=[pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixturePinDigest}} }
        if ($Mode -eq 'resident_dictionary') { return [pscustomobject]@{models=@{name='chiqiongblastfuenace:latest';digest=$script:FixturePinDigest}} }
        if ($Mode -eq 'resident_api_error') { throw [InvalidOperationException]::new($global:FixtureSecret) }
        if ($Mode -eq 'resident_after_error' -and $global:ResidentReads -gt 2) { throw [IO.IOException]::new($global:FixtureSecret) }
        if ($Mode -eq 'resident_after_null' -and $global:ResidentReads -gt 2) { return [pscustomobject]@{models=$null} }
        if ($Mode -eq 'post_status_drift' -and $global:StatusReads -gt 0) { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixtureOtherDigest}) }
        return [pscustomobject]@{models=@($global:Loaded)}
    }
    if ($Uri -notin $script:Catalog.status_endpoints) { throw 'Unexpected network operation' }
    $global:StatusReads++
    $Port=if ($Uri -match ':8093/') {8093} else {8094}
    $Prefix='status'+$Port+'_'
    if ($Mode -eq ($Prefix+'timeout') -or $Mode -eq 'status_error') { throw [TimeoutException]::new($global:FixtureSecret) }
    if ($Mode -eq ($Prefix+'connection')) { throw [Net.Http.HttpRequestException]::new($global:FixtureSecret,[Net.Sockets.SocketException]::new(10061)) }
    if ($Mode -eq ($Prefix+'http')) { throw [Net.Http.HttpRequestException]::new($global:FixtureSecret,$null,[Net.HttpStatusCode]::ServiceUnavailable) }
    if ($Mode -eq ($Prefix+'nested')) { throw [InvalidOperationException]::new($global:FixtureSecret,[TimeoutException]::new($global:FixtureSecret)) }
    if ($Mode -eq ($Prefix+'task_timeout')) { throw [Threading.Tasks.TaskCanceledException]::new($global:FixtureSecret,[TimeoutException]::new($global:FixtureSecret)) }
    if ($Mode -eq ($Prefix+'cancel')) { throw [OperationCanceledException]::new($global:FixtureSecret) }
    if ($Mode -eq ($Prefix+'missing')) { return [pscustomobject]@{} }
    if ($Mode -eq ($Prefix+'false')) { return [pscustomobject]@{model_ok=$false} }
    if ($Mode -eq ($Prefix+'truthy')) { return [pscustomobject]@{model_ok='true'} }
    return [pscustomobject]@{model_ok=$true}
}
function Invoke-Ollama {
    param($Arguments)
    if (($Arguments -join '|') -ne 'cp|chiqiongblastfuenace:1|chiqiongblastfuenace:latest') { throw 'Another model CLI operation forbidden' }
    $global:Calls.Add('restore_same_fixed_alias')
    [IO.File]::AppendAllText((Join-Path $Workdir 'mutation-trace.txt'),"restore_same_fixed_alias`n",$Utf8)
    if ($Mode -eq 'cp_error') { throw [IO.IOException]::new($global:FixtureSecret) }
    if ($Mode -ne 'alias_recheck_error') { $global:Alias=$script:FixturePinDigest }
}
function Invoke-Warmup {
    $global:Calls.Add('warmup_same_fixed_base')
    [IO.File]::AppendAllText((Join-Path $Workdir 'mutation-trace.txt'),"warmup_same_fixed_base`n",$Utf8)
    if ($global:Alias -ne $script:FixturePinDigest) { throw 'Warmup of another base forbidden' }
    if ($Mode -eq 'warmup_error') { throw [InvalidOperationException]::new($global:FixtureSecret,[TimeoutException]::new($global:FixtureSecret)) }
    if ($Mode -eq 'warmup_cancel') { throw [OperationCanceledException]::new($global:FixtureSecret) }
    if ($Mode -eq 'warmup_alias_drift') { $global:Alias=$script:FixtureOtherDigest }
    if ($Mode -eq 'warmup_wrong_resident') { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixtureOtherDigest}) }
    elseif ($Mode -ne 'warmup_no_resident') { $global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixturePinDigest}) }
    return [pscustomobject]@{skipped=$false}
}
function Test-StatusEndpoints { throw 'Legacy combined dependency check forbidden' }
function Ensure-OllamaService { throw 'Service operation forbidden in guard test' }
function Ensure-ModelTag { throw 'Rebuild or bootstrap forbidden' }
function Set-HealthTaskPaused { throw 'Task operation forbidden in guard test' }
. $GuardFile
$Failed=$false
$Message=''
$ExceptionType=$null
$InnerType=$null
$Result=$null
try {
    switch ($Mode) {
        'switch_same' { $ModelId='fixed';$Result=Invoke-Switch }
        'switch_other' { $ModelId='other';$Result=Invoke-Switch }
        'sanitize' { $Result=Invoke-Sanitize }
        'direct_other' { $Result=Activate-Model -Model $script:Catalog.models[1] -DesiredModelId 'other' -ActionName 'Switch' -FallbackActive $false }
        'direct_fallback' { $Result=Activate-Model -Model $script:Catalog.models[0] -DesiredModelId 'fixed' -ActionName 'Repair' -FallbackActive $true }
        'initialize' { $Result=Initialize-State }
        'initialize_empty' { $Result=Initialize-State }
        'initialize_wrong' { $Result=Initialize-State }
        'initialize_multiple' { $Result=Initialize-State }
        default { $Result=Invoke-Repair }
    }
} catch { $Failed=$true;$Message=$_.Exception.Message;$ExceptionType=$_.Exception.GetType().FullName;if ($null -ne $_.Exception.InnerException) {$InnerType=$_.Exception.InnerException.GetType().FullName} }
$State=$null
if (Test-Path -LiteralPath $script:Catalog.state_path) { $State=Get-Content -LiteralPath $script:Catalog.state_path -Raw | ConvertFrom-Json }
@{failed=$Failed;message=$Message;exception_type=$ExceptionType;inner_exception_type=$InnerType;alias=$global:Alias;loaded=@($global:Loaded);state=$State;
 calls=@($global:Calls.ToArray());events=@($global:Events.ToArray());result=$Result;resident_reads=$global:ResidentReads;status_reads=$global:StatusReads} | ConvertTo-Json -Depth 20
