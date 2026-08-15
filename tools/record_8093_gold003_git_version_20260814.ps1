[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Script = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold003_20260814\remote_record_8093_mcp_gold_git_version.ps1'
& $Script `
    -ExecutionId 'mcp-gold003-20260814-1119-r3' `
    -ExpectedParentHead '6a5ca5afb5225ba67364857af194438af6d297dd' `
    -ExpectedCrossSourceSha256 'B55662599F05696773FB7761C74945217D08EABE67931235B638B5A9EFE6D8F5' `
    -ExpectedDomainRouterSha256 'D33B33CBABD379B8D20C29AEA295E4C023874FCF7229A6296D6F3EF38798257F' `
    -Profile 'gold003' `
    -RequirementId 'BUG-MCP-GOLD003-MISSING-PTOP-20260814'
exit $LASTEXITCODE
