# REQ-QA-SINGLE-BASE-MODEL-20260917. Injected library; no top-level I/O.
function Get-FixedProperty {
    param([object]$Value,[string]$Name)
    if ($null -eq $Value) { return $null }
    if ($Value -is [Collections.IDictionary]) { return ,$Value[$Name] }
    $Property=$Value.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $null }
    return ,$Property.Value
}

function Get-FixedModelPin {
    $Name='chiqiongblastfuenace:latest'
    $Digest='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    $Matches=@($script:Catalog.models | Where-Object { [string]$_.preferred_digest -ceq $Digest })
    if ($Matches.Count -ne 1 -or [string]$script:Catalog.public_alias -cne $Name -or
            [string]$Matches[0].version_tag -cne 'chiqiongblastfuenace:1') { throw 'fixed_catalog_invalid' }
    return [pscustomobject]@{name=$Name;digest=$Digest;weight_digest='31629f53165ab6a7dad8c9847dcfd1fdf55829dac1e6e748f4a68581b0033d34';model=$Matches[0]}
}

function Write-FixedStageEvent {
    param([string]$Stage,[string]$Outcome,[string]$Code,[object]$ErrorRecord)
    $Data=@{stage=$Stage;outcome=$Outcome;code=$Code;expected_digest='e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124';
        actual_installed_digest=$script:FixedObservation.installed;actual_alias_digest=$script:FixedObservation.alias;
        actual_resident_digest=$script:FixedObservation.resident;exception_type=$null;inner_exception_types=@();http_status=$null;failure_kind='none'}
    if ($null -ne $ErrorRecord) {
        $Exception=$ErrorRecord.Exception
        $Data.exception_type=$Exception.GetType().FullName
        $Types=@()
        $Current=$Exception
        $Data.failure_kind='contract_error'
        for ($Index=0;$Index -lt 4 -and $null -ne $Current;$Index++) {
            if ($Current -is [TimeoutException]) { $Data.failure_kind='timeout' }
            elseif ($Current -is [OperationCanceledException]) { $Data.failure_kind='cancelled' }
            elseif ($Current -is [Net.Sockets.SocketException]) { $Data.failure_kind='connection_error' }
            elseif ($Current -is [IO.IOException]) { $Data.failure_kind='io_error' }
            $Response=Get-FixedProperty $Current 'Response'
            $Status=Get-FixedProperty $Response 'StatusCode'
            if ($null -eq $Status) { $Status=Get-FixedProperty $Current 'StatusCode' }
            if ($null -ne $Status) { try { $Data.http_status=[int]$Status } catch {} }
            $Current=$Current.InnerException
            if ($null -ne $Current) { $Types+=$Current.GetType().FullName }
        }
        $Data.inner_exception_types=$Types
        if ($null -ne $Data.http_status) { $Data.failure_kind='http_error' }
    }
    if ($Outcome -eq 'failed') { $script:FixedLastFailure=$Data }
    try { Write-Event -Level $(if ($Outcome -eq 'failed') {'error'} else {'info'}) -Event 'fixed_model_stage' -Data $Data }
    catch {
        $LoggingError=$_
        $Current=$LoggingError.Exception
        $Cancelled=$false
        $TimedOut=$false
        while ($null -ne $Current) {
            if ($Current -is [OperationCanceledException] -or $Current -is [Management.Automation.PipelineStoppedException]) { $Cancelled=$true }
            if ($Current -is [TimeoutException]) { $TimedOut=$true }
            $Current=$Current.InnerException
        }
        if ($Cancelled -and -not $TimedOut) { throw [OperationCanceledException]::new('fixed_operation_cancelled',$LoggingError.Exception) }
        $script:FixedObservation.logging_ok=$false
    }
}

function Invoke-FixedStage {
    param([string]$Stage,[scriptblock]$Operation)
    Write-FixedStageEvent -Stage $Stage -Outcome 'started' -Code 'stage_started'
    try {
        $Value=& $Operation
        if ($Stage -eq 'state-write' -and $Value -is [Collections.IDictionary]) {
            # The operation has persisted pending=false health. Cancellation here leaves that safe state.
            Write-FixedStageEvent -Stage $Stage -Outcome 'pending' -Code 'state_pending_written'
            $Value.recovery_complete=$true
            $Value.observability_ok=$script:FixedObservation.logging_ok
            $Value.assistant_ready=($Value.identity_ready -and $Value.dependencies_ready -and $Value.observability_ok)
            Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $Value
        } else {
            Write-FixedStageEvent -Stage $Stage -Outcome 'passed' -Code 'stage_passed'
        }
        return $Value
    } catch {
        $Record=$_
        # Logging cancellation must not replace an already captured operation failure.
        try { Write-FixedStageEvent -Stage $Stage -Outcome 'failed' -Code ('fixed_'+$Stage+'_failed') -ErrorRecord $Record }
        catch { $script:FixedObservation.logging_ok=$false }
        $Current=$Record.Exception
        $Cancelled=$false
        $TimedOut=$false
        while ($null -ne $Current) {
            if ($Current -is [OperationCanceledException] -or $Current -is [Management.Automation.PipelineStoppedException]) { $Cancelled=$true }
            if ($Current -is [TimeoutException]) { $TimedOut=$true }
            $Current=$Current.InnerException
        }
        if ($Cancelled -and -not $TimedOut) { throw [OperationCanceledException]::new('fixed_operation_cancelled',$Record.Exception) }
        throw [InvalidOperationException]::new(('fixed_'+$Stage+'_failed'),$Record.Exception)
    }
}

function Get-FixedResidentSnapshot {
    param([object]$Pin)
    $script:FixedObservation.resident=$null
    $Response=Invoke-RestMethod -Method Get -Uri "$($script:Catalog.api_base)/api/ps" -TimeoutSec 6
    $Raw=Get-FixedProperty $Response 'models'
    if ($null -eq $Raw -or $Raw -is [string] -or $Raw -is [Collections.IDictionary] -or $Raw -isnot [Collections.IEnumerable]) { throw 'resident_list_unknown' }
    $Loaded=@($Raw)
    if ($Loaded.Count -eq 1) {
        $Actual=[string](Get-FixedProperty $Loaded[0] 'digest')
        if ($Actual -cmatch '^[a-f0-9]{64}$') { $script:FixedObservation.resident=$Actual }
    }
    if ($Loaded.Count -gt 1 -or ($Loaded.Count -eq 1 -and
            ([string](Get-FixedProperty $Loaded[0] 'digest') -cne $Pin.digest -or
             [string](Get-FixedProperty $Loaded[0] 'name') -cne $Pin.name))) { throw 'resident_identity_mismatch' }
    return [pscustomobject]@{resident=($Loaded.Count -eq 1);digest=$script:FixedObservation.resident}
}

function Assert-FixedInstalledVersion {
    param([object]$Pin)
    $script:FixedObservation.installed=$null
    $Version=Test-ModelTag $Pin.model
    $Actual=[string](Get-FixedProperty $Version 'digest')
    if ($Actual -cmatch '^[a-f0-9]{64}$') { $script:FixedObservation.installed=$Actual }
    if ($null -eq $Version -or $Actual -cne $Pin.digest) { throw 'installed_identity_mismatch' }
}

function Assert-FixedPublicAlias {
    param([object]$Pin)
    $script:FixedObservation.alias=$null
    $Public=@(Get-PublicTag)
    if ($Public.Count -eq 1) {
        $Actual=[string](Get-FixedProperty $Public[0] 'digest')
        if ($Actual -cmatch '^[a-f0-9]{64}$') { $script:FixedObservation.alias=$Actual }
    }
    if ($Public.Count -ne 1 -or [string](Get-FixedProperty $Public[0] 'digest') -cne $Pin.digest -or
            [string](Get-FixedProperty $Public[0] 'name') -cne $Pin.name) { throw 'alias_identity_mismatch' }
}

function Get-FixedDependencyHealth {
    $Checks=@()
    foreach ($Port in @(8093,8094)) {
        $Stage='status'+$Port
        $Allowed='http://127.0.0.1:'+$Port+'/api/ollama/status'
        $Endpoints=@($script:Catalog.status_endpoints | Where-Object { [string]$_ -ceq $Allowed })
        try {
            $Result=Invoke-FixedStage -Stage $Stage -Operation {
                if ($Endpoints.Count -ne 1) { throw 'dependency_endpoint_missing' }
                $Response=Invoke-RestMethod -Method Get -Uri $Allowed -TimeoutSec 20
                if ((Get-FixedProperty $Response 'model_ok') -isnot [bool] -or
                    (Get-FixedProperty $Response 'model_ok') -ne $true) { throw 'dependency_model_not_ready' }
                return [pscustomobject]@{service=$Stage;ok=$true;code='dependency_ready';failure_kind='none';http_status=$null}
            }
            $Checks+=$Result
        } catch [OperationCanceledException] { throw }
        catch { $Checks+=[pscustomobject]@{service=$Stage;ok=$false;code=('fixed_'+$Stage+'_failed');failure_kind=$script:FixedLastFailure.failure_kind;http_status=$script:FixedLastFailure.http_status} }
    }
    return $Checks
}

function New-FixedModelState {
    param([object]$Pin,[string]$ActionName,[bool]$IdentityReady,[object[]]$Status)
    $DependenciesReady=($Status.Count -eq 2 -and @($Status | Where-Object {$_.ok -ne $true}).Count -eq 0)
    return [ordered]@{
        schema_version=1;desired_model_id=[string]$Pin.model.id;effective_model_id=$(if ($IdentityReady) {[string]$Pin.model.id} else {$null})
        public_alias=[string]$Pin.name;effective_version_tag=$(if ($IdentityReady) {[string]$Pin.model.version_tag} else {$null})
        digest=$script:FixedObservation.resident;fallback_active=$false;context_length=[int]$Pin.model.context_length
        updated_at=Get-UtcTimestamp;last_action=$ActionName;last_error=$(if ($DependenciesReady) {$null} else {'dependency_degraded'})
        identity_locked=$IdentityReady;identity_ready=$IdentityReady;model_switch_allowed=$false
        dependencies_ready=$DependenciesReady;dependency_status=$Status;observability_ok=$script:FixedObservation.logging_ok
        recovery_complete=$false;assistant_ready=$false
    }
}

function Activate-Model {
    param([object]$Model,[string]$DesiredModelId,[string]$ActionName,[bool]$FallbackActive)
    $Pin=Get-FixedModelPin
    if ([string]$Model.id -cne [string]$Pin.model.id -or [string]$Model.version_tag -cne [string]$Pin.model.version_tag -or
            [string]$Model.preferred_digest -cne $Pin.digest -or $DesiredModelId -cne [string]$Pin.model.id -or $FallbackActive) { throw 'activation_forbidden' }
    # Direct activation receives its own observations; Repair retains the verified preceding stages.
    if ($null -eq (Get-Variable -Name FixedObservation -Scope Script -ErrorAction SilentlyContinue)) {
        $script:FixedObservation=@{installed=$null;alias=$null;resident=$null;logging_ok=$true}
    }
    Invoke-FixedStage 'installed-version-check' { Assert-FixedInstalledVersion $Pin }
    Invoke-FixedStage 'alias-check' { Assert-FixedPublicAlias $Pin }
    $Before=Invoke-FixedStage 'resident-before' { Get-FixedResidentSnapshot $Pin }
    $Warmup=if ($Before.resident) { [pscustomobject]@{skipped=$true;reason='fixed_base_already_resident'} }
        else { Invoke-FixedStage 'warmup' { Invoke-Warmup } }
    Invoke-FixedStage 'alias-check' { Assert-FixedPublicAlias $Pin }
    Invoke-FixedStage 'resident-after' {
        if (-not (Get-FixedResidentSnapshot $Pin).resident) { throw 'fixed_resident_absent' }
    }
    $Status=@(Get-FixedDependencyHealth)
    # Dependency checks may take time: identity is re-observed before any successful state write.
    Invoke-FixedStage 'alias-check' { Assert-FixedPublicAlias $Pin }
    Invoke-FixedStage 'resident-after' {
        if (-not (Get-FixedResidentSnapshot $Pin).resident) { throw 'fixed_resident_absent' }
    }
    $State=Invoke-FixedStage 'state-write' {
        $NewState=New-FixedModelState -Pin $Pin -ActionName $ActionName -IdentityReady $true -Status $Status
        Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $NewState
        return $NewState
    }
    return [pscustomobject]@{state=$State;alias_changed=$false;warmup=$Warmup;status=$Status;identity_locked=$true;
        identity_ready=$true;assistant_ready=($State.assistant_ready -and $script:FixedObservation.logging_ok);observability_ok=$script:FixedObservation.logging_ok}
}

function Initialize-State {
    $script:FixedObservation=@{installed=$null;alias=$null;resident=$null;logging_ok=$true}
    $Pin=Invoke-FixedStage 'installed-version-check' { Get-FixedModelPin }
    Invoke-FixedStage 'installed-version-check' { Assert-FixedInstalledVersion $Pin }
    Invoke-FixedStage 'alias-check' { Assert-FixedPublicAlias $Pin }
    $Resident=Invoke-FixedStage 'resident-before' { Get-FixedResidentSnapshot $Pin }
    if (-not $Resident.resident) { throw 'initialize_identity_not_ready' }
    $State=Invoke-FixedStage 'state-write' {
        $NewState=New-FixedModelState -Pin $Pin -ActionName 'InitializeFixedBase' -IdentityReady $true -Status @()
        Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $NewState
        return $NewState
    }
    return $State
}

function Invoke-Switch { throw 'model_switch_forbidden' }
function Invoke-Sanitize { throw 'model_mutation_forbidden' }

function Invoke-Repair {
    $script:FixedObservation=@{installed=$null;alias=$null;resident=$null;logging_ok=$true}
    $Pin=Invoke-FixedStage 'installed-version-check' { Get-FixedModelPin }
    Invoke-FixedStage 'installed-version-check' { Assert-FixedInstalledVersion $Pin }
    $Resident=Invoke-FixedStage 'resident-before' { Get-FixedResidentSnapshot $Pin }
    $AliasReady=Invoke-FixedStage 'alias-check' {
        $script:FixedObservation.alias=$null
        $Public=@(Get-PublicTag)
        if ($Public.Count -gt 1) { throw 'alias_list_invalid' }
        if ($Public.Count -eq 0) { return $false }
        $Actual=[string](Get-FixedProperty $Public[0] 'digest')
        if ($Actual -cnotmatch '^[a-f0-9]{64}$' -or [string](Get-FixedProperty $Public[0] 'name') -cne $Pin.name) { throw 'alias_list_invalid' }
        $script:FixedObservation.alias=$Actual
        return ($Actual -ceq $Pin.digest)
    }
    $AliasChanged=$false
    if (-not $AliasReady) {
        Invoke-FixedStage 'alias-repair' {
            Invoke-Ollama -Arguments @('cp',[string]$Pin.model.version_tag,[string]$Pin.name) | Out-Null
            Assert-FixedPublicAlias $Pin
        }
        $AliasChanged=$true
        $After=Invoke-FixedStage 'resident-after' { Get-FixedResidentSnapshot $Pin }
        if ($Resident.resident -and -not $After.resident) { throw 'alias_repair_lost_resident' }
    }
    $Result=Activate-Model -Model $Pin.model -DesiredModelId ([string]$Pin.model.id) -ActionName 'RepairFixedBase' -FallbackActive $false
    $Result.alias_changed=$AliasChanged
    return $Result
}
