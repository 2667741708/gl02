# Frozen activation dependency fixture; no top-level execution or credentials.
# Candidate SHA256 ed9cd6652852ef488170fa625eec2f44ac4270d0dd21e9cb920f5783a2da12c5.
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
    if (-not $ModelId) {
        throw "-ModelId is required for Action Switch."
    }
    Ensure-OllamaService
    $target = Get-ModelDefinition $ModelId
    $oldState = Initialize-State
    $rollbackModel = Get-ModelDefinition ([string]$oldState.effective_model_id)
    Ensure-ModelTag $rollbackModel | Out-Null
    $healthPaused = $false
    $healthWasEnabled = Get-HealthTaskEnabled
    try {
        if ($healthWasEnabled) {
            $healthPaused = $true
            Set-HealthTaskPaused $true
        }
        return Activate-Model -Model $target -DesiredModelId ([string]$target.id) -ActionName "Switch" -FallbackActive $false
    } catch {
        if ($null -ne (Test-ModelTag $rollbackModel)) {
            Invoke-Ollama -Arguments @("cp", [string]$rollbackModel.version_tag, [string]$script:Catalog.public_alias) | Out-Null
            if (-not $SkipWarmup) {
                Invoke-Warmup | Out-Null
            }
        }
        if ($null -ne $oldState) {
            Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $oldState
        }
        Write-Event -Level "error" -Event "switch_failed" -Data @{ model_id = $ModelId; error = $_.Exception.Message }
        throw
    } finally {
        if ($healthPaused) {
            Set-HealthTaskPaused $false
        }
    }
}
