# OPS-QA-MODEL-REPAIR-STABILITY-20260917. Functions only; loading performs no I/O.
function Get-RepairPolicyPath {
    return ([string]$script:Catalog.state_path) + '.repair-policy.json'
}

function Read-RepairPolicy {
    $Path = Get-RepairPolicyPath
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @{schema_version=1; failures=@{}}
    }
    $Policy = Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if ($Policy.schema_version -ne 1 -or $Policy.failures -isnot [Collections.IDictionary]) {
        throw 'Invalid repair cooldown policy; no model activation attempted'
    }
    return $Policy
}

function Test-RepairCandidateCooling {
    param([Collections.IDictionary]$Policy, [string]$CandidateId, [DateTimeOffset]$Now)
    if (-not $Policy.failures.Contains($CandidateId)) { return $false }
    $Failure = $Policy.failures[$CandidateId]
    if ($Failure -isnot [Collections.IDictionary] -or -not $Failure.Contains('retry_after')) {
        throw 'Invalid candidate cooldown record; no model activation attempted'
    }
    $Until = [DateTimeOffset]::Parse([string]$Failure.retry_after, [Globalization.CultureInfo]::InvariantCulture)
    return $Now -lt $Until
}

function New-RepairCandidateFailure {
    param([Collections.IDictionary]$Policy, [string]$CandidateId, [DateTimeOffset]$Now)
    $Count = 1
    if ($Policy.failures.Contains($CandidateId)) {
        $Previous = $Policy.failures[$CandidateId]
        if ($Previous -isnot [Collections.IDictionary] -or $Previous.attempts -isnot [long] -and $Previous.attempts -isnot [int] -or $Previous.attempts -lt 1) {
            throw 'Invalid candidate failure count'
        }
        $Count = [math]::Min([long]$Previous.attempts + 1, 1000000)
    }
    $Seconds = [int][math]::Min(900, 60 * [math]::Pow(2, [math]::Min($Count - 1, 4)))
    return @{attempts=[long]$Count; failed_at=$Now.ToUniversalTime().ToString('o'); retry_after=$Now.AddSeconds($Seconds).ToUniversalTime().ToString('o'); cooldown_seconds=$Seconds}
}
