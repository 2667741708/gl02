[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$DeployScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_window_fix_20260814\remote_guarded_deploy_8093_mcp_gold.ps1'
& $DeployScript `
    -StageRoot 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_window_fix_20260814' `
    -ExpectedManifestSha256 '23BB7F09634FA8670B0FD869C1A930202860C980F148F393EFB91F249C068AF2' `
    -ExecutionId 'body-temp-window-20260814-1502-r2' `
    -ExpectedGitHead '67d2434cbbb69591ff8e35d4027fd47acfa37850' `
    -AcceptanceProfile 'body_temperature_statistics' `
    -RequirementId 'BUG-MCP-BODY-WINDOW-ROLLING-DURATION-20260814'
exit $LASTEXITCODE
