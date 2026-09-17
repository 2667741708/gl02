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
 models=@([pscustomobject]@{id='fixed';version_tag='synthetic:fixed';preferred_digest=$script:FixturePinDigest;context_length=32768},
          [pscustomobject]@{id='other';version_tag='synthetic:other';preferred_digest=$script:FixtureOtherDigest;context_length=32768})}
$global:Alias=$script:FixturePinDigest
$global:Loaded=@([pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$script:FixturePinDigest})
$global:Calls=[Collections.Generic.List[string]]::new()
if ($Mode -in @('alias_repair','cp_error')) { $global:Alias=$script:FixtureOtherDigest }
if ($Mode -eq 'empty_resident') { $global:Loaded=@() }
if ($Mode -eq 'wrong_resident') { $global:Loaded=@([pscustomobject]@{digest=$script:FixtureOtherDigest}) }
if ($Mode -eq 'multiple_residents') { $global:Loaded=@([pscustomobject]@{digest=$script:FixturePinDigest},[pscustomobject]@{digest=$script:FixtureOtherDigest}) }
if ($Mode -eq 'bad_catalog') { $script:Catalog.models[0].preferred_digest=$script:FixtureOtherDigest }
function Get-PublicTag { return [pscustomobject]@{name='chiqiongblastfuenace:latest';digest=$global:Alias} }
function Test-ModelTag { param($Model) if ($Mode -eq 'missing_fixed') {return $null}; return [pscustomobject]@{digest=$Model.preferred_digest} }
function Get-UtcTimestamp { return [DateTimeOffset]::UtcNow.ToString('o') }
function Write-JsonFileAtomic { param($Path,$Value) [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 12),$Utf8) }
function Write-Event { param($Level,$Event,$Data) $global:Calls.Add('event_'+$Event) }
function Invoke-RestMethod {
    param($Method,$Uri,$TimeoutSec)
    if ($Method -ne 'Get' -or $Uri -ne 'synthetic-api/api/ps') { throw 'Unexpected network operation' }
    return [pscustomobject]@{models=@($global:Loaded)}
}
function Invoke-Ollama {
    param($Arguments)
    if (($Arguments -join '|') -ne 'cp|synthetic:fixed|chiqiongblastfuenace:latest') { throw 'Another model CLI operation forbidden' }
    $global:Calls.Add('restore_same_fixed_alias')
    if ($Mode -eq 'cp_error') { throw 'synthetic same-alias restoration failure' }
    $global:Alias=$script:FixturePinDigest
}
function Invoke-Warmup {
    $global:Calls.Add('warmup_same_fixed_base')
    if ($global:Alias -ne $script:FixturePinDigest) { throw 'Warmup of another base forbidden' }
    if ($Mode -eq 'warmup_error') { throw 'synthetic same-base warmup failure' }
    $global:Loaded=@([pscustomobject]@{digest=$script:FixturePinDigest})
    return [pscustomobject]@{skipped=$false}
}
function Test-StatusEndpoints { if ($Mode -eq 'status_error') {throw 'synthetic status failure'};return @([pscustomobject]@{ok=$true}) }
function Ensure-OllamaService { throw 'Service operation forbidden in the guard test' }
function Ensure-ModelTag { throw 'Rebuild or bootstrap forbidden' }
function Set-HealthTaskPaused { throw 'Task operation forbidden in the guard test' }
. $GuardFile
$Failed=$false
$Message=''
if ($Mode -eq 'warmup_error') { $global:Loaded=@() }
try {
    switch ($Mode) {
        'switch_same' { $ModelId='fixed';$Result=Invoke-Switch }
        'switch_other' { $ModelId='other';$Result=Invoke-Switch }
        'sanitize' { $Result=Invoke-Sanitize }
        'direct_other' { $Result=Activate-Model -Model $script:Catalog.models[1] -DesiredModelId 'other' -ActionName 'Switch' -FallbackActive $false }
        'direct_fallback' { $Result=Activate-Model -Model $script:Catalog.models[0] -DesiredModelId 'fixed' -ActionName 'Repair' -FallbackActive $true }
        'initialize' { $Result=Initialize-State }
        default { $Result=Invoke-Repair }
    }
} catch { $Failed=$true;$Message=$_.Exception.Message }
$State=$null
if (Test-Path -LiteralPath $script:Catalog.state_path) { $State=Get-Content -LiteralPath $script:Catalog.state_path -Raw | ConvertFrom-Json }
@{failed=$Failed;message=$Message;alias=$global:Alias;loaded=@($global:Loaded);state=$State;calls=@($global:Calls.ToArray())} | ConvertTo-Json -Depth 12
