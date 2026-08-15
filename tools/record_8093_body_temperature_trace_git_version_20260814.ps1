[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Recorder = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_trace_20260814\remote_record_8093_mcp_gold_git_version.ps1'
& $Recorder `
    -ExecutionId 'body-temperature-trace-20260814-2046-r3' `
    -ExpectedParentHead '32130a518f77061633d2fdb32a7cd65033453fa3' `
    -ExpectedFrontendSha256 'E63D80BEAB1AF72CD0650252881FEA70E9831D26CF0762BB97D03735A45B6B1A' `
    -ExpectedProxySha256 '3F46FD86D458EA73B7060841BBCB6C017E7521E1F28A39651700965C997C59C2' `
    -ExpectedDomainRouterSha256 '92C8015FE14A26DD48B86D2CBE6C612C28F054F4EE06A284D25EC0CFE06F886D' `
    -Profile 'body_trace' `
    -RequirementId 'REQ-QA-COMPOSITE-MCP-EXECUTION-TRACE-20260814'
exit $LASTEXITCODE
