[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold003_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -ExecutionId 'mcp-gold003-20260814-1119-r3' `
    -ExpectedManifestSha256 '7EA40C77B9708903D849D80ABF6C86095BA8FB4252AA6D2DB9FF385E5B4F5628' `
    -ExpectedGitHead '6a5ca5afb5225ba67364857af194438af6d297dd' `
    -AcceptanceProfile 'gold003' `
    -RequirementId 'BUG-MCP-GOLD003-MISSING-PTOP-20260814' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold003_20260814'
exit $LASTEXITCODE
