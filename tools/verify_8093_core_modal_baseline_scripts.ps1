[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This verification requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Scripts = @(
    Join-Path $Root 'tools\remote_preflight_8093_core_modal_baseline.ps1'
    Join-Path $Root 'tools\remote_guarded_deploy_8093_core_modal_baseline.ps1'
    Join-Path $Root 'tools\deploy_8093_core_modal_baseline_22012.ps1'
)

$Results = @()
foreach ($Path in $Scripts) {
    $Tokens = $null
    $Errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count) { throw "PowerShell parse failed for $Path`: $($Errors[0].Message)" }
    $Text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if (-not $Text.Contains("PSEdition -ne 'Core'")) { throw "PowerShell 7 gate missing: $Path" }
    if (-not $Text.Contains('[Text.UTF8Encoding]::new($false)')) { throw "UTF-8 runtime missing: $Path" }
    $Results += [pscustomobject]@{ path = $Path; parsed = $true; utf8 = $true }
}

$Remote = Get-Content -LiteralPath $Scripts[1] -Raw -Encoding UTF8
foreach ($Contract in @(
    'Global\BFV4PreviewProxy8093Deployment',
    'Stop-8093',
    'Start-8093',
    'finally',
    'rollback_applied',
    'dashboard-main-CcxwpZA4.js',
    'data-baseline-evidence'
)) {
    if (-not $Remote.Contains($Contract)) { throw "Remote deployment contract missing: $Contract" }
}
foreach ($Port in @(8094, 8768, 8770, 5432, 8892, 11434)) {
    if (-not $Remote.Contains([string]$Port)) { throw "Protected port missing: $Port" }
}

[pscustomobject]@{ ok = $true; scripts = $Results } | ConvertTo-Json -Depth 5
