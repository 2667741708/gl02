[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_statistics_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_statistics_20260814' `
    -ExpectedManifestSha256 'FD7051EB92C5C6470AC3A35A840BB105286026C19287AF5BDDFB1743309207C9' `
    -ExecutionId 'body-temp-stats-20260814-1455-r1' `
    -ExpectedGitHead '67d2434cbbb69591ff8e35d4027fd47acfa37850' `
    -AcceptanceProfile 'body_temperature_statistics' `
    -RequirementId 'REQ-MCP-BODY-LAYER-STATISTICS-20260814'
exit $LASTEXITCODE
