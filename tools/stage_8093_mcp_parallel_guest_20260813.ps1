[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Script = 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_tools\stage_abc33_contextual_assistant_8093_package.ps1'
& $Script `
    -ExecutionId 'mcp5-guest-20260813-1137' `
    -ExpectedManifestSha256 '8EB2A3FD7A6892E7DEAD150E9969B705271057EEBD5EAE1CFCD789857405E006' `
    -Incoming 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_incoming' `
    -PackageName 'mcp_parallel_guest_8093_20260813.zip' `
    -HashFileName 'mcp_parallel_guest_8093_20260813.sha256' `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\mcp_parallel_guest_20260813_stage'
exit $LASTEXITCODE
