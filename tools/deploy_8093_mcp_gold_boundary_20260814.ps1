[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold_boundary_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -ExecutionId 'mcp-gold-boundary-20260814-1142-r1' `
    -ExpectedManifestSha256 'ABFB5A1C067F890E6640C0872DFF8FB5DDC89A37DAD1195A561C4AA14C3CE32C' `
    -ExpectedGitHead '82d71c69c378e6ae1990a4b6234939caf2bdc296' `
    -AcceptanceProfile 'boundary_security' `
    -RequirementId 'BUG-MCP-GOLD-RUNTIME-BOUNDARIES-20260814' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold_boundary_20260814'
exit $LASTEXITCODE
