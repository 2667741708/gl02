$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This preparation requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Template = '.codex\skills\deploy-8093-guarded-update\assets\remote_guarded_deploy_8093.ps1.template'
$Output = 'tools\remote_guarded_deploy_abc33_overview_entry_8093.ps1'
$Text = Get-Content -LiteralPath $Template -Raw -Encoding UTF8
$Text = $Text.Replace('__REQUIREMENT_ID__', 'BUG-8093-ABC33-OVERVIEW-ENTRY-20260811')
$Text = $Text.Replace('__FEATURE___YYYYMMDD', 'abc33_overview_entry_20260811')
$Text = $Text.Replace('__FEATURE___8093_', 'abc33_overview_entry_8093_')
$FeatureCheck = @'
    $Asset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=abc33-20260811-overview-entry-r1&deploy=$Stamp" -TimeoutSec 30
    if (-not $Page.Content.Contains('abc33-20260811-overview-entry-r1')) { throw '8093 page cache version marker missing.' }
    if (-not $Asset.Content.Contains('BUG-8093-ABC33-OVERVIEW-ENTRY-20260811')) { throw 'ABC33 overview-entry asset marker missing.' }
    if (-not $Asset.Content.Contains("overview-furnace-panel-v12 > .panel-head")) { throw 'ABC33 overview panel anchor missing.' }
    if ($Asset.Content.Contains('abc33-entry-fallback')) { throw 'Forbidden fixed fallback remains in served asset.' }
'@
$Text = $Text.Replace('    # Add feature-specific page, asset, API, browser, and marker checks here.', $FeatureCheck.TrimEnd())
[IO.File]::WriteAllText((Join-Path (Get-Location) $Output), $Text, $Utf8NoBom)

& node --check '高炉前端数据\assets\abc-furnace-rules-production.js'
if ($LASTEXITCODE -ne 0) { throw 'ABC33 JavaScript syntax validation failed.' }
& python -m pytest -q tests/test_abc_production_ui.py tests/test_abc_rule_engine.py tests/test_abc_public_review_labels.py
if ($LASTEXITCODE -ne 0) { throw 'ABC33 contract tests failed.' }
& node tools/verify_abc33_overview_entry_standard.cjs
if ($LASTEXITCODE -ne 0) { throw 'ABC33 standard browser validation failed.' }

[ordered]@{
    ok = $true
    requirement_id = 'BUG-8093-ABC33-OVERVIEW-ENTRY-20260811'
    remote_payload = (Resolve-Path -LiteralPath $Output).Path
    validation_tier = 'standard'
} | ConvertTo-Json -Depth 4
