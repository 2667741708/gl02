[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_trace_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -ExecutionId 'body-temperature-trace-20260814-2046-r3' `
    -ExpectedManifestSha256 '92703E6E6CA63B8E0AC5D1000FB8A8F6A58C14644D36FDCE3DE15346DD1AC8EB' `
    -ExpectedGitHead '32130a518f77061633d2fdb32a7cd65033453fa3' `
    -AcceptanceProfile 'body_temperature_trace' `
    -RequirementId 'REQ-QA-COMPOSITE-MCP-EXECUTION-TRACE-20260814' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_trace_20260814'
exit $LASTEXITCODE
