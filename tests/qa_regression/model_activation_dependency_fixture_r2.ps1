# Frozen activation dependency fixture; no top-level execution or credentials.
# Candidate SHA256 37cc7582d9dee079c010cd5f7b2e58289ca9f23fd6cfe0a3950f414a44c59f94.
# Actual Activate-Model unchanged from read-only production baseline 856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa.
function Test-PublicAliasResident {
    param([string]$ExpectedDigest)

    $loaded = @((Invoke-RestMethod -Method Get -Uri "$($script:Catalog.api_base)/api/ps" -TimeoutSec 20).models)
    return $loaded.Count -eq 1 -and @(
        $loaded | Where-Object {
            [string]$_.name -eq [string]$script:Catalog.public_alias -and
            [string]$_.digest -eq $ExpectedDigest
        }
    ).Count -eq 1
}

function Activate-Model {
    param(
        [object]$Model,
        [string]$DesiredModelId,
        [string]$ActionName,
        [bool]$FallbackActive
    )

    $tag = Ensure-ModelTag $Model
    $publicBefore = @(Get-PublicTag)
    $aliasChanged = $publicBefore.Count -ne 1 -or [string]$publicBefore[0].digest -ne [string]$tag.digest
    if ($aliasChanged) {
        Invoke-Ollama -Arguments @("cp", [string]$Model.version_tag, [string]$script:Catalog.public_alias) | Out-Null
    }
    $residentBefore = Test-PublicAliasResident -ExpectedDigest ([string]$tag.digest)
    $needsWarmup = $aliasChanged -or -not $residentBefore
    $warmup = if ($needsWarmup) { Invoke-Warmup } else { [pscustomobject]@{ skipped = $true; reason = "already_resident" } }
    $publicAfter = @(Get-PublicTag)
    if ($publicAfter.Count -ne 1 -or [string]$publicAfter[0].digest -ne [string]$tag.digest) {
        throw "Public alias digest does not match selected model."
    }
    if (-not (Test-PublicAliasResident -ExpectedDigest ([string]$tag.digest))) {
        throw "Public alias is not resident after activation."
    }
    $status = @(Test-StatusEndpoints)
    $state = [ordered]@{
        schema_version = 1
        desired_model_id = $DesiredModelId
        effective_model_id = [string]$Model.id
        public_alias = [string]$script:Catalog.public_alias
        effective_version_tag = [string]$Model.version_tag
        digest = [string]$tag.digest
        fallback_active = $FallbackActive
        context_length = [int]$Model.context_length
        updated_at = Get-UtcTimestamp
        last_action = $ActionName
        last_error = $null
    }
    Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $state
    Write-Event -Level "info" -Event "model_activated" -Data @{ desired_model_id = $DesiredModelId; effective_model_id = [string]$Model.id; alias_changed = $aliasChanged; fallback_active = $FallbackActive }
    return [pscustomobject]@{ state = $state; alias_changed = $aliasChanged; warmup = $warmup; status = $status }
}

function Invoke-Switch {
    if (-not $ModelId) { throw '-ModelId is required for Action Switch.' }
    Ensure-OllamaService
    $target = Get-ModelDefinition $ModelId
    $previousState = Initialize-State
    $publicBefore = @(Get-PublicTag)
    if ($publicBefore.Count -ne 1) { throw 'No single public alias to snapshot; run Repair before Switch.' }
    $rollbackModel = Find-ModelByDigest ([string]$publicBefore[0].digest)
    if ($null -eq $rollbackModel) { throw 'Previous public alias is not approved; run Repair before Switch.' }
    $rollbackVersion = Test-ModelTag $rollbackModel
    if ($null -eq $rollbackVersion -or [string]$rollbackVersion.digest -ne [string]$publicBefore[0].digest) {
        throw 'Previous approved alias lacks a matching installed rollback version.'
    }
    $oldDesired = [string]$previousState.desired_model_id
    $oldState = [ordered]@{
        schema_version=1; desired_model_id=$oldDesired; effective_model_id=[string]$rollbackModel.id
        public_alias=[string]$script:Catalog.public_alias; effective_version_tag=[string]$rollbackModel.version_tag
        digest=[string]$publicBefore[0].digest; fallback_active=([string]$rollbackModel.id -ne $oldDesired)
        context_length=[int]$rollbackModel.context_length; updated_at=Get-UtcTimestamp
        last_action='SwitchSnapshot'; last_error=$null
    }
    $healthPaused = $false
    $healthWasEnabled = Get-HealthTaskEnabled
    $activationStarted = $false
    try {
        if ($healthWasEnabled) {
            $healthPaused = $true
            Set-HealthTaskPaused $true
        }
        $activationStarted = $true
        return Activate-Model -Model $target -DesiredModelId ([string]$target.id) -ActionName 'Switch' -FallbackActive $false
    } catch {
        $switchError = $_
        try {
            $after = @(Get-PublicTag)
            $aliasChanged = $after.Count -ne 1 -or [string]$after[0].digest -ne [string]$publicBefore[0].digest
            if ($aliasChanged) {
                Invoke-Ollama -Arguments @('cp', [string]$rollbackModel.version_tag, [string]$script:Catalog.public_alias) | Out-Null
            }
            $restored = @(Get-PublicTag)
            if ($restored.Count -ne 1 -or [string]$restored[0].digest -ne [string]$publicBefore[0].digest) {
                throw 'Switch alias restoration was not verified.'
            }
            $oldState.last_action = 'SwitchRollback'
            $oldState.last_error = 'switch_failed'
            $oldState.updated_at = Get-UtcTimestamp
            Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $oldState
            if ($activationStarted -and $aliasChanged -and -not $SkipWarmup -and
                    -not (Test-PublicAliasResident -ExpectedDigest ([string]$publicBefore[0].digest))) {
                Invoke-Warmup | Out-Null
            }
        } catch {
            Write-Event -Level 'error' -Event 'switch_rollback_failed' -Data @{model_id=$ModelId; error=$_.Exception.Message}
            throw 'Switch failed and restoration is incomplete; no successful activation claimed.'
        }
        Write-Event -Level 'error' -Event 'switch_failed' -Data @{model_id=$ModelId; error=$switchError.Exception.Message}
        throw $switchError
    } finally {
        if ($healthPaused) { Set-HealthTaskPaused $false }
    }
}
