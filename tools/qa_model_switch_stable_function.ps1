# Function-only candidate: rollback follows the observed alias, never stale state.
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
