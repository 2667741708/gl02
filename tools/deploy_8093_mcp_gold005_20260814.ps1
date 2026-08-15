[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedManifestSha256,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -ExecutionId $ExecutionId `
    -ExpectedManifestSha256 $ExpectedManifestSha256 `
    -ExpectedGitHead '89091ab6a82f27f8142653805ffb49d2a229f2b4' `
    -AcceptanceProfile 'gold005_dependency' `
    -RequirementId 'BUG-MCP-GOLD005-DEPENDENCY-GATE-20260814' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814'
exit $LASTEXITCODE
