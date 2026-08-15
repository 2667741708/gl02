[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Script = 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_tools\remote_deploy_abc33_contextual_assistant_8093.ps1'
& $Script `
    -ExecutionId 'mcp5-guest-20260813-1137' `
    -ExpectedManifestSha256 '8EB2A3FD7A6892E7DEAD150E9969B705271057EEBD5EAE1CFCD789857405E006' `
    -RequirementId 'REQ-8093-MCP-PARALLEL-5-AND-GUEST-DEPLOY-20260813' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_stage' `
    -GuestSharedAcceptance
exit $LASTEXITCODE
