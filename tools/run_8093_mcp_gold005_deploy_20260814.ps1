[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814' `
    -ExpectedManifestSha256 'AA0F346214133EF580F6BFFF6D4700B5B3910B495FC12E4EE6CB05941FF4E547' `
    -ExecutionId 'mcp-gold005-20260814-1205-r2' `
    -ExpectedGitHead '89091ab6a82f27f8142653805ffb49d2a229f2b4' `
    -AcceptanceProfile 'gold005_dependency' `
    -RequirementId 'BUG-MCP-GOLD005-DEPENDENCY-GATE-20260814'
exit $LASTEXITCODE
