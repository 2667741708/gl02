[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Scripts = @(
    'tools\remote_guarded_deploy_8093_mcp_gold.ps1',
    'tools\prepare_8093_body_temperature_statistics_release.ps1',
    'tools\prepare_8093_body_temperature_window_fix_release.ps1',
    'tools\prepare_8093_body_temperature_answer_integrity_release.ps1',
    'tools\run_8093_body_temperature_statistics_deploy_20260814.ps1',
    'tools\run_8093_body_temperature_window_fix_deploy_20260814.ps1',
    'tools\run_8093_body_temperature_answer_integrity_deploy_20260814.ps1',
    'tools\stage_8093_body_temperature_statistics_release.ps1',
    'tools\stage_8093_body_temperature_window_fix_release.ps1',
    'tools\stage_8093_body_temperature_answer_integrity_release.ps1',
    'tools\remote_record_8093_mcp_gold_git_version.ps1',
    'tools\run_8093_body_temperature_statistics_git_save_20260814.ps1',
    'tools\stage_8093_body_temperature_statistics_git_save.ps1',
    'tools\remote_review_8093_git_gate.ps1',
    'tools\remote_probe_8093_body_stats_targets.ps1',
    'tools\remote_probe_8093_body_temperature_failures.ps1'
)
$Rows = @()
foreach ($Relative in $Scripts) {
    $Path = Join-Path $Root $Relative
    $Tokens = $null
    $Errors = $null
    [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors) | Out-Null
    if ($Errors.Count -gt 0) {
        throw "PowerShell AST failed for $Relative`: $($Errors[0].Message)"
    }
    $Rows += [ordered]@{ path = $Relative; ast_errors = 0 }
}
[ordered]@{
    schema = 'bf.body-temperature-statistics-release-verification.v1'
    ok = $true
    scripts = $Rows
} | ConvertTo-Json -Depth 5
