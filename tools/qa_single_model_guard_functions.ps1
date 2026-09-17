# REQ-QA-SINGLE-BASE-MODEL-20260917. Injected library; no top-level I/O.
function Get-FixedModelPin {
    $Name='chiqiongblastfuenace:latest'
    $Digest='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    $Matches=@($script:Catalog.models | Where-Object { [string]$_.preferred_digest -eq $Digest })
    if ($Matches.Count -ne 1 -or [string]$script:Catalog.public_alias -ne $Name) { throw 'Fixed base catalog binding changed; no model operation allowed.' }
    return [pscustomobject]@{name=$Name;digest=$Digest;model=$Matches[0]}
}

function Get-FixedResidentSnapshot {
    param([object]$Pin)
    $Loaded=@((Invoke-RestMethod -Method Get -Uri "$($script:Catalog.api_base)/api/ps" -TimeoutSec 6).models)
    if ($Loaded.Count -gt 1 -or ($Loaded.Count -eq 1 -and [string]$Loaded[0].digest -ne [string]$Pin.digest)) {
        throw 'A different base is resident; switching or unloading it is forbidden.'
    }
    return [pscustomobject]@{resident=($Loaded.Count -eq 1);digest=[string]$Pin.digest}
}

function Assert-FixedInstalledVersion {
    param([object]$Pin)
    $Version=Test-ModelTag $Pin.model
    if ($null -eq $Version -or [string]$Version.digest -ne [string]$Pin.digest) {
        throw 'Fixed installed base is missing or changed; downloading or rebuilding another base is forbidden.'
    }
}

function Assert-FixedPublicAlias {
    param([object]$Pin)
    $Public=@(Get-PublicTag)
    if ($Public.Count -ne 1 -or [string]$Public[0].digest -ne [string]$Pin.digest) {
        throw 'Public alias does not match the immutable base; no model request allowed.'
    }
}

function New-FixedModelState {
    param([object]$Pin,[string]$ActionName)
    return [ordered]@{
        schema_version=1;desired_model_id=[string]$Pin.model.id;effective_model_id=[string]$Pin.model.id
        public_alias=[string]$Pin.name;effective_version_tag=[string]$Pin.model.version_tag
        digest=[string]$Pin.digest;fallback_active=$false;context_length=[int]$Pin.model.context_length
        updated_at=Get-UtcTimestamp;last_action=$ActionName;last_error=$null
        identity_locked=$true;model_switch_allowed=$false
    }
}

function Activate-Model {
    param([object]$Model,[string]$DesiredModelId,[string]$ActionName,[bool]$FallbackActive)
    $Pin=Get-FixedModelPin
    if ([string]$Model.id -ne [string]$Pin.model.id -or [string]$Model.version_tag -ne [string]$Pin.model.version_tag -or
            [string]$Model.preferred_digest -ne [string]$Pin.digest -or $DesiredModelId -ne [string]$Pin.model.id -or $FallbackActive) {
        throw 'Activation of another base or fallback is forbidden.'
    }
    Assert-FixedInstalledVersion $Pin
    Assert-FixedPublicAlias $Pin
    $Before=Get-FixedResidentSnapshot $Pin
    $Warmup=if ($Before.resident) { [pscustomobject]@{skipped=$true;reason='fixed_base_already_resident'} } else { Invoke-Warmup }
    Assert-FixedPublicAlias $Pin
    if (-not (Get-FixedResidentSnapshot $Pin).resident) { throw 'The identical fixed base is not resident after warmup.' }
    $Status=@(Test-StatusEndpoints)
    $State=New-FixedModelState -Pin $Pin -ActionName $ActionName
    Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $State
    Write-Event -Level 'info' -Event 'fixed_model_ready' -Data @{model_id=[string]$Pin.model.id;identity_locked=$true;model_switch_allowed=$false}
    return [pscustomobject]@{state=$State;alias_changed=$false;warmup=$Warmup;status=$Status;identity_locked=$true}
}

function Initialize-State {
    $Pin=Get-FixedModelPin
    Assert-FixedInstalledVersion $Pin
    Assert-FixedPublicAlias $Pin
    $Resident=Get-FixedResidentSnapshot $Pin
    $State=New-FixedModelState -Pin $Pin -ActionName 'InitializeFixedBase'
    Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $State
    return $State
}

function Invoke-Switch {
    throw 'Model switching is disabled by the immutable-base policy, including approved alternatives.'
}

function Invoke-Sanitize {
    throw 'Model mutation is disabled by the immutable-base policy.'
}

function Invoke-Repair {
    $Pin=Get-FixedModelPin
    Assert-FixedInstalledVersion $Pin
    $Resident=Get-FixedResidentSnapshot $Pin
    $Public=@(Get-PublicTag)
    if ($Public.Count -ne 1 -or [string]$Public[0].digest -ne [string]$Pin.digest) {
        # Restore only the alias of this same frozen base, never select a new base.
        # Any different loaded base was rejected before this metadata operation.
        Invoke-Ollama -Arguments @('cp',[string]$Pin.model.version_tag,[string]$Pin.name) | Out-Null
        Assert-FixedPublicAlias $Pin
        $After=Get-FixedResidentSnapshot $Pin
        if ($Resident.resident -and -not $After.resident) { throw 'Alias restoration lost the fixed resident; no alternative or retry allowed.' }
    }
    return Activate-Model -Model $Pin.model -DesiredModelId ([string]$Pin.model.id) -ActionName 'RepairFixedBase' -FallbackActive $false
}
