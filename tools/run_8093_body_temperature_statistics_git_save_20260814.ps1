[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$SaveScript = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_statistics_git_20260814\remote_record_8093_mcp_gold_git_version.ps1'
& $SaveScript `
    -ExecutionId 'body-temp-stats-20260814-1502-git' `
    -ExpectedParentHead '67d2434cbbb69591ff8e35d4027fd47acfa37850' `
    -ExpectedProxySha256 '8F543E96A4A071FE604838A20FFB657381BC67DC516FE0775A60A7A157650D8E' `
    -ExpectedCrossSourceSha256 'A99CF6E4FD73F11CEDBEC01F254FF649615C96FEB55827F92C57853021D55033' `
    -ExpectedExtendedSha256 'DFCCB886D6842E1F05698BD7217F95EAEAD2D8F1F2D424EA8F4EF14BF66AEF91' `
    -ExpectedCalculationCatalogSha256 'B84CDF5D857E3406AFBAC277EEA249EB48DB1D69E47F6D68CD781DF8170FACA4' `
    -Profile 'body_stats' `
    -RequirementId 'REQ-MCP-BODY-LAYER-STATISTICS-20260814'
exit $LASTEXITCODE
