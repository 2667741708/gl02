[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Root = Split-Path -Parent $PSScriptRoot
$Scripts = @('remote_preflight_qa_routing_v3.ps1','remote_guarded_deploy_qa_routing_v3_8093.ps1','record_qa_routing_v3_version.ps1')
foreach ($Name in $Scripts) {
    $Tokens = $null
    $Errors = $null
    $Path = Join-Path $PSScriptRoot $Name
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -ne 0) { throw "Release script parse failed: $Name" }
    $Text = [IO.File]::ReadAllText($Path, $Utf8)
    if (-not $Text.Contains("ValidateSet('V3','V4','V5','V6','V7','V8','V9','V10','V11','V12','V13','V14','V15','V16','V17','V18','V19','V20')")) { throw "Version gate missing: $Name" }
}
$Deployer = [IO.File]::ReadAllText((Join-Path $PSScriptRoot $Scripts[1]), $Utf8)
$ReadonlyPath = Join-Path $PSScriptRoot 'invoke_qa_document_candidate_readonly.ps1'
$ReadonlyTokens = $null
$ReadonlyErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile($ReadonlyPath, [ref]$ReadonlyTokens, [ref]$ReadonlyErrors)
if ($ReadonlyErrors.Count -ne 0) { throw 'Read-only candidate invocation parse failed' }
foreach ($Marker in @('Global\BFV4PreviewProxy8093Deployment','Check-Protected $Before','finally','Assert-Baselines','guard_restored')) {
    if (-not $Deployer.Contains($Marker)) { throw "Deployment safety marker missing: $Marker" }
}
@{ok=$true;schema='bf.qa.routing.release-script-check.v1';parsed=$Scripts;ps_version=$PSVersionTable.PSVersion.ToString()} | ConvertTo-Json -Depth 4
