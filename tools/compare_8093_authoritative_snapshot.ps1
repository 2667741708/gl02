[CmdletBinding()]
param([string]$SnapshotPath = 'docs\handoffs\8093_authoritative_snapshot.latest.json')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$SnapshotPath = (Resolve-Path -LiteralPath (Join-Path $Root $SnapshotPath)).Path
$Snapshot = Get-Content -LiteralPath $SnapshotPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Snapshot.secret_values_included) { throw 'Snapshot unexpectedly contains secret values.' }
$ServiceConfigRelative = 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$RequiredSafeEnvironment = [ordered]@{
    BF_QA_KNOWLEDGE_SEARCH_MODE = 'keyword'
    BF_QA_GUEST_ENABLED = '1'
    BF_QA_MCP_MAX_TOOL_ROUNDS = '5'
    BF_QA_MCP_MAX_TOOL_CALLS = '5'
    BF_QA_MCP_PARALLEL_TOOL_CALLS = '1'
    BF_QA_MCP_MAX_PARALLEL_TOOL_CALLS = '5'
}
$Rows = @()
foreach ($Property in $Snapshot.file_hashes.PSObject.Properties) {
    $LocalPath = Join-Path $Root $Property.Name
    $LocalExists = Test-Path -LiteralPath $LocalPath -PathType Leaf
    $LocalHash = if ($LocalExists) { (Get-FileHash -LiteralPath $LocalPath -Algorithm SHA256).Hash } else { $null }
    $ComparisonMode = 'byte_equal'
    $InSync = $LocalExists -and $Property.Value.exists -and $LocalHash -eq [string]$Property.Value.sha256
    $SemanticChecks = $null
    if ($Property.Name -eq $ServiceConfigRelative) {
        # The remote service file can contain credentials.  Never copy it locally or
        # require byte equality; compare only the approved non-secret runtime contract.
        $ComparisonMode = 'redacted_semantic_contract'
        $LocalConfig = Get-Content -LiteralPath $LocalPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $SemanticChecks = @()
        foreach ($Entry in $RequiredSafeEnvironment.GetEnumerator()) {
            $LocalValue = [string]$LocalConfig.env.($Entry.Key)
            $RemoteValue = [string]$Snapshot.service_config.env_redacted.($Entry.Key)
            $SemanticChecks += [ordered]@{
                name = $Entry.Key
                expected = $Entry.Value
                local_matches = $LocalValue -eq $Entry.Value
                remote_matches = $RemoteValue -eq $Entry.Value
            }
        }
        $InSync = @($SemanticChecks | Where-Object { -not $_.local_matches -or -not $_.remote_matches }).Count -eq 0
    }
    $Rows += [ordered]@{
        path = $Property.Name
        comparison_mode = $ComparisonMode
        local_exists = $LocalExists
        remote_exists = [bool]$Property.Value.exists
        local_sha256 = $LocalHash
        remote_sha256 = [string]$Property.Value.sha256
        semantic_checks = $SemanticChecks
        in_sync = $InSync
    }
}
[ordered]@{
    ok = @($Rows | Where-Object { -not $_.in_sync }).Count -eq 0
    schema = 'bf.8093.authoritative-local-compare.v1'
    snapshot_generated_at = $Snapshot.generated_at
    compared_at = (Get-Date).ToString('o')
    rows = $Rows
} | ConvertTo-Json -Depth 7
