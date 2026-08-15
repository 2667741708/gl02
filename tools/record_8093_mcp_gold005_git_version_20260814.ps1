[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Script = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_mcp_gold005_20260814\remote_record_8093_mcp_gold_git_version.ps1'
& $Script `
    -ExecutionId 'mcp-gold005-20260814-1205-r2' `
    -ExpectedParentHead '89091ab6a82f27f8142653805ffb49d2a229f2b4' `
    -ExpectedProxySha256 'B0FD19BFAFD403B7A37A62CC7FDC743185A2F20EBEF03075D99923163F8BEBD4' `
    -Profile 'proxy_only' `
    -RequirementId 'BUG-MCP-GOLD005-DEPENDENCY-GATE-20260814'
exit $LASTEXITCODE
