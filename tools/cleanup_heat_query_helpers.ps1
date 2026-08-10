$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$names = @(
  '_patch_heat_query_local.ps1',
  'patch_heat_performance_query_v2.ps1',
  'apply_heat_performance_query_v2_safe.ps1',
  'apply_heat_performance_query_v2_safe_ascii.ps1',
  'update_heat_patch_filter.ps1',
  'update_heat_patch_filter2.ps1',
  'update_heat_patch_source_scope.ps1',
  'update_heat_patch_strict_tail.ps1',
  'update_heat_patch_strict_tail2.ps1',
  'update_heat_patch_strict_tail3.ps1',
  'update_heat_patch_proxy_normalize.ps1',
  'update_heat_patch_newitem.ps1',
  'update_heat_quality_test_contract.ps1',
  'update_heat_query_empty_state.ps1',
  'update_heat_query_empty_state_b64.ps1',
  'update_heat_query_empty_state_dynamic.ps1',
  'update_heat_query_sample_label.ps1',
  'update_heat_query_sample_label_codes.ps1',
  'update_heat_query_test_param_assertions.ps1',
  'update_heat_query_test_param_assertions2.ps1',
  'patch_heat_service_tank_mapping.ps1',
  'fix_heat_service_tank_mapping_newline.ps1',
  'update_remote_heat_query_script_add_heat_service.ps1',
  'update_heat_query_show_tank_list.ps1'
)
foreach ($name in $names) {
  $path = Join-Path $root "tools\$name"
  if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
Write-Output 'heat-query-temp-helpers-removed'
