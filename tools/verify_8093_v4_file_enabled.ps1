$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $PSScriptRoot
$path = Get-ChildItem -LiteralPath $root -Filter 'frontend_dashboard_v3.server.html' -Recurse -File |
  Where-Object { $_.FullName -like '*frontend_dashboard_v3.server.html' } |
  Sort-Object FullName |
  Select-Object -First 1 -ExpandProperty FullName
if (-not $path) {
  throw "frontend_dashboard_v3.server.html not found under $root"
}
$item = Get-Item -LiteralPath $path
$text = Get-Content -LiteralPath $path -Raw
$lastCompactMetricRows = $text.LastIndexOf('MetricRows=function({buf}){return <div className="metric-list compact-core-metrics"')
$lastGroupedMetricRows = [Math]::Max(
  [Math]::Max(
    $text.LastIndexOf('function MetricRows({buf,diagnosis}){'),
    $text.LastIndexOf('MetricRows=function({buf,diagnosis}){')
  ),
  [Math]::Max(
    $text.LastIndexOf('MetricRows=function({buf}){const[page,setPage]=useState(0),groups=CORE_METRIC_PAGES'),
    [Math]::Max(
      $text.LastIndexOf('MetricRows=function({buf}){const left=CORE_METRIC_LEFT_GROUPS_V4'),
      $text.LastIndexOf('MetricRows=function BFCoreMetricRowsV7')
    )
  )
)
$hasFinalCoreGroupsOverride = $text.Contains('OPS-8093-CORE-GROUPS-FINAL') -or ($lastGroupedMetricRows -gt $lastCompactMetricRows)
$service = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewProxy8093'"
$port = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$process = $null
if ($port) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($port.OwningProcess)" -ErrorAction SilentlyContinue
}

[pscustomobject]@{
  TargetPath = $item.FullName
  Length = $item.Length
  LastWriteTime = $item.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
  HasResponsiveMarker = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-RESPONSIVE-OVERVIEW' -Quiet)
  HasResponsiveScript = [bool](Select-String -LiteralPath $path -Pattern 'ops-responsive-overview-css' -Quiet)
  HasCoreGroups = [bool](Select-String -LiteralPath $path -Pattern 'CORE_METRIC_GROUPS' -Quiet)
  HasGroupedMetrics = [bool](Select-String -LiteralPath $path -Pattern 'core-grouped-metrics' -Quiet)
  HasCoreSpark30MinThin = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-SPARK-30MIN-THIN' -Quiet)
  HasCoreDensitySparkV3 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-DENSITY-SPARK-V3' -Quiet)
  HasFurnaceLayerCallouts = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-FURNACE-LAYER-CALLOUTS' -Quiet)
  HasFurnaceLayerDom = [bool](Select-String -LiteralPath $path -Pattern 'furnace-layer-callouts' -Quiet)
  HasDiagnosisNormalGreen = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-DIAGNOSIS-NORMAL-GREEN' -Quiet)
  HasFurnacePointAnchorsV2 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-FURNACE-POINT-ANCHORS-V2' -Quiet)
  HasFurnaceFollowAnchorsV3 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-FURNACE-FOLLOW-ANCHORS-V3' -Quiet)
  HasCadTooltipFallback = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK' -Quiet)
  HasCadGhostBandsFix = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CAD-GHOST-BANDS-FIX' -Quiet)
  HasCoreTwoColumnV4 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-TWO-COLUMN-V4' -Quiet)
  HasCoreTwoColumnBalanced14x14 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-TWO-COLUMN-V4-BALANCED-14-14' -Quiet)
  HasCoreTwoColumnFillLargeV5 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-TWO-COLUMN-V5-FILL-LARGE' -Quiet)
  HasCoreValueAlignV6 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-VALUE-ALIGN-V6' -Quiet)
  HasCoreValueTabularNums = [bool](Select-String -LiteralPath $path -Pattern 'font-variant-numeric:tabular-nums!important' -Quiet)
  HasCoreValueDDIN = [bool](Select-String -LiteralPath $path -Pattern 'font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important' -Quiet -SimpleMatch)
  HasCoreTwoColumnDom = [bool](Select-String -LiteralPath $path -Pattern 'core-two-column-v4' -Quiet)
  HasCoreTwoPageV7 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-TWO-PAGE-V7' -Quiet)
  HasCoreTwoPageDom = [bool](Select-String -LiteralPath $path -Pattern 'core-page-v7' -Quiet)
  HasCoreTwoPageV7SpecificityFix = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX' -Quiet)
  HasCoreSparkGapV10 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-CORE-SPARK-GAP-V10' -Quiet)
  HasCoreValueLeftAlign = [bool](Select-String -LiteralPath $path -Pattern 'text-align:left!important' -Quiet -SimpleMatch)
  HasOverviewLargeTrendV8 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-OVERVIEW-LARGE-TREND-V8' -Quiet)
  HasOverviewLargeTrendDom = [bool](Select-String -LiteralPath $path -Pattern 'overview-large-trend-grid-v8' -Quiet)
  HasOverviewDecisionHubV11 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-OVERVIEW-DECISION-HUB-V11' -Quiet)
  HasOverviewDecisionHubDom = [bool](Select-String -LiteralPath $path -Pattern 'overview-right-v11' -Quiet)
  HasAutoMonitorDockMdV9 = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-AUTO-MONITOR-DOCK-MD-V9' -Quiet)
  HasAutoMonitorMarkdownRenderer = [bool](Select-String -LiteralPath $path -Pattern 'bf-auto-summary.bf-auto-md' -Quiet)
  HasOptimizationNoteRemoved = [bool](Select-String -LiteralPath $path -Pattern 'OPS-8093-OPTIMIZATION-NOTE-REMOVED' -Quiet)
  HasRemovedOptimizationNoteText = -not [bool](Select-String -LiteralPath $path -Pattern '<div className="focus-principle">{opt.isNormal?' -Quiet -SimpleMatch)
  LastCompactMetricRowsIndex = $lastCompactMetricRows
  LastGroupedMetricRowsIndex = $lastGroupedMetricRows
  EffectiveCoreGroups = $hasFinalCoreGroupsOverride
  ServiceName = $service.Name
  ServiceState = $service.State
  ServiceStartMode = $service.StartMode
  ListenPort = if ($port) { $port.LocalPort } else { $null }
  ListenPid = if ($port) { $port.OwningProcess } else { $null }
  ProcessCommandLine = if ($process) { $process.CommandLine } else { $null }
} | ConvertTo-Json -Depth 4
