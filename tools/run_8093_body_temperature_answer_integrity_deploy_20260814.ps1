[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_answer_integrity_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_answer_integrity_20260814' `
    -ExpectedManifestSha256 'F569E586994F16B1850D9BCA1AB78486B114C230A25963403D97CD670E10C3D5' `
    -ExecutionId 'body-temp-answer-integrity-20260814-r6' `
    -ExpectedGitHead '849d9554060f7c1252722e8394a9cb224ff13488' `
    -AcceptanceProfile 'body_temperature_statistics' `
    -RequirementId 'BUG-MCP-BODY-STATS-ANSWER-INTEGRITY-20260814'
exit $LASTEXITCODE
