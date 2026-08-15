[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Scripts = @(
    'tools\remote_probe_8093_qa_copy_recommendations.ps1',
    'tools\remote_guarded_deploy_8093_qa_copy_recommendations.ps1',
    'tools\remote_record_8093_qa_copy_recommendations_git.ps1'
)
foreach ($Relative in $Scripts) {
    $Path = Join-Path $Root $Relative
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count) { throw "PowerShell parse failed: $Relative; $($Errors[0].Message)" }
    Write-Output "AST_OK $Relative"
}
