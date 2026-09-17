# Replacement function only; the candidate builder preserves every other action.
function Invoke-Repair {
    Ensure-OllamaService
    $state = Initialize-State
    $desiredId = [string]$state.desired_model_id

    # An approved healthy fallback stays resident. Preference changes require Switch.
    $public = @(Get-PublicTag)
    if ($public.Count -eq 1) {
        $current = Find-ModelByDigest ([string]$public[0].digest)
        if ($null -ne $current) {
            $version = Test-ModelTag $current
            if ($null -ne $version -and [string]$version.digest -eq [string]$public[0].digest -and
                    (Test-PublicAliasResident -ExpectedDigest ([string]$version.digest))) {
                # Status endpoint failure must not start changing a healthy alias.
                return Activate-Model -Model $current -DesiredModelId $desiredId -ActionName 'RepairResident' -FallbackActive ([string]$current.id -ne $desiredId)
            }
        }
    }

    $policy = Read-RepairPolicy
    $candidateIds = @($desiredId) + @($script:Catalog.fallback_order | Where-Object { [string]$_ -ne $desiredId })
    $failures = @()
    $healthPaused = $false
    $healthWasEnabled = Get-HealthTaskEnabled
    try {
        foreach ($candidateId in $candidateIds) {
            $now = [DateTimeOffset]::UtcNow
            if (Test-RepairCandidateCooling -Policy $policy -CandidateId ([string]$candidateId) -Now $now) {
                Write-Event -Level 'info' -Event 'repair_candidate_cooling' -Data @{model_id=[string]$candidateId}
                continue
            }
            $candidate = Get-ModelDefinition ([string]$candidateId)
            $version = Test-ModelTag $candidate
            $publicBefore = @(Get-PublicTag)
            $stateBefore = Read-State
            $rollbackModel = $null
            if ($publicBefore.Count -eq 1) {
                $knownBefore = Find-ModelByDigest ([string]$publicBefore[0].digest)
                if ($null -ne $knownBefore) {
                    $rollbackVersion = Test-ModelTag $knownBefore
                    if ($null -ne $rollbackVersion -and [string]$rollbackVersion.digest -eq [string]$publicBefore[0].digest) {
                        $rollbackModel = $knownBefore
                    }
                }
            }
            $needsMutation = $null -eq $version -or $publicBefore.Count -ne 1 -or ($null -ne $version -and [string]$publicBefore[0].digest -ne [string]$version.digest)
            if ($needsMutation -and $healthWasEnabled -and -not $healthPaused) {
                # Restoration ownership starts before a pause operation can partially fail.
                $healthPaused = $true
                Set-HealthTaskPaused $true
            }
            try {
                $result = Activate-Model -Model $candidate -DesiredModelId $desiredId -ActionName 'Repair' -FallbackActive ([string]$candidate.id -ne $desiredId)
                return $result
            } catch {
                $candidateError = $_
                if ($null -ne $rollbackModel) {
                    $after = @(Get-PublicTag)
                    if ($after.Count -ne 1 -or [string]$after[0].digest -ne [string]$publicBefore[0].digest) {
                        Invoke-Ollama -Arguments @('cp', [string]$rollbackModel.version_tag, [string]$script:Catalog.public_alias) | Out-Null
                    }
                    $restored = @(Get-PublicTag)
                    if ($restored.Count -ne 1 -or [string]$restored[0].digest -ne [string]$publicBefore[0].digest) {
                        throw 'Repair alias rollback failed; no next candidate attempted'
                    }
                }
                if ($null -ne $stateBefore) {
                    Write-JsonFileAtomic -Path ([string]$script:Catalog.state_path) -Value $stateBefore
                }
                $policy.failures[[string]$candidateId] = New-RepairCandidateFailure -Policy $policy -CandidateId ([string]$candidateId) -Now ([DateTimeOffset]::UtcNow)
                Write-JsonFileAtomic -Path (Get-RepairPolicyPath) -Value $policy
                $failures += [pscustomobject]@{model_id=[string]$candidateId; error=$candidateError.Exception.Message; alias_rollback_available=($null -ne $rollbackModel)}
                Write-Event -Level 'warning' -Event 'repair_candidate_failed' -Data @{model_id=[string]$candidateId; error=$candidateError.Exception.Message; alias_rollback_available=($null -ne $rollbackModel)}
            }
        }
        throw 'No candidate restored; failures or cooldown recorded, no healthy residency claimed'
    } finally {
        if ($healthPaused) { Set-HealthTaskPaused $false }
        if ($failures.Count -gt 0) { Write-Event -Level 'warning' -Event 'repair_failures' -Data @{failures=$failures} }
    }
}
