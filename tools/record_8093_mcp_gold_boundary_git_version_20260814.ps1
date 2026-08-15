[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Script = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold_boundary_20260814\remote_record_8093_mcp_gold_git_version.ps1'
& $Script `
    -ExecutionId 'mcp-gold-boundary-20260814-1142-r1' `
    -ExpectedParentHead '82d71c69c378e6ae1990a4b6234939caf2bdc296' `
    -ExpectedProxySha256 '20B0AA5057F52DE8142DD4827DCFF3457B6E74779C6D3E7F4317324C7FEA7C09' `
    -ExpectedCrossSourceSha256 'F042842B56782B99B2707805841EE0C4382106ED184D4C26EBBD1C5F48629181' `
    -ExpectedDiagnosisReviewAssetSha256 '0A058DDE71461F7C6FF894331A664D749A20392757B19E1E10739AEC2FE62E45' `
    -Profile 'boundary' `
    -RequirementId 'BUG-MCP-GOLD-RUNTIME-BOUNDARIES-20260814'
exit $LASTEXITCODE
