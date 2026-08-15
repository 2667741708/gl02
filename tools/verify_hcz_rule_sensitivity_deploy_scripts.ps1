[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This verifier requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Scripts = @(
    'tools\prepare_hcz_rule_sensitivity_8093_release.ps1',
    'tools\deploy_hcz_rule_sensitivity_22012.ps1',
    'tools\remote_probe_hcz_rule_sensitivity_8093.ps1',
    'tools\remote_validate_hcz_rule_sensitivity_stage.ps1',
    'tools\remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1'
)
$RequiredMarkers = @(
    'REQ-HCZ-RULE-SENSITIVITY-20260811',
    'Global\BFV4PreviewProxy8093Deployment',
    'BFV4PreviewProxy8093',
    'hcz-rule-sensitivity'
)

$Results = @()
foreach ($RelativePath in $Scripts) {
    $Path = Join-Path $Root $RelativePath
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -gt 0) {
        throw "PowerShell parse failure in $RelativePath`: $($Errors[0].Message)"
    }
    $Results += [ordered]@{ path = $RelativePath; parsed = $true }
}

$RemoteText = Get-Content -LiteralPath (Join-Path $Root 'tools\remote_guarded_deploy_hcz_rule_sensitivity_8093.ps1') -Raw -Encoding UTF8
foreach ($Marker in $RequiredMarkers) {
    if (-not $RemoteText.Contains($Marker)) { throw "Remote deploy marker missing: $Marker" }
}
if ($RemoteText.Contains('Stop-Service -Name BFV4PreviewWs8768')) { throw 'Remote deploy must not stop 8768.' }

[ordered]@{
    ok = $true
    script_count = $Results.Count
    scripts = $Results
} | ConvertTo-Json -Depth 4
