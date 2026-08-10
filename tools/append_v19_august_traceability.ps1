$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath '.').Path
$lines = @(
  '',
  '## REQ-SI-V19-AUGUST-HOLDOUT-20260807',
  '',
  'V19 rolling update: July data is included in offline training through 2026-07-26 19:02:00; 158 new August heats are held out as time-out evaluation. Original V19 artifacts remain frozen.',
  '',
  'Implementation: train_v19_august_holdout.py and train_v19_august_holdout_v2.py. Results: EXP-SI-V19-AUGUST-HOLDOUT-20260807.',
  '',
  'The protocol-selected candidate is pci; all_context is promising on this single August window but cannot be selected from the test result. No production promotion.',
  '',
  'Status: completed_offline_time_out_validation.',
  ''
)
$section = $lines -join [Environment]::NewLine
$names = @('requirements_traceability.md','program_index.md','question_traceability.md','data_contract.md','test_reference.md')
foreach ($name in $names) {
  $matches = Get-ChildItem -Path (Join-Path $root ('PT\*\docs\' + $name)) -File -ErrorAction SilentlyContinue
  foreach ($file in $matches) {
    $text = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8
    if ($text -notmatch 'REQ-SI-V19-AUGUST-HOLDOUT-20260807') { Add-Content -LiteralPath $file.FullName -Value $section -Encoding UTF8 }
  }
}
