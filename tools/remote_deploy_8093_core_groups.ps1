$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$serviceName = "BFV4PreviewProxy8093"
$htmlPath = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$patchScript = Join-Path $root "tools\patch_22012_8093_core_metric_groups.py"
$verifyScript = Join-Path $root "tools\verify_8093_v4_file_enabled.ps1"
$python = "C:\Program Files\Python311\python.exe"

function Wait-PortState {
  param(
    [Parameter(Mandatory=$true)][int]$Port,
    [Parameter(Mandatory=$true)][bool]$ShouldListen,
    [int]$Seconds = 30
  )
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (($null -ne $conn) -eq $ShouldListen) {
      return $conn
    }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach expected listen state: $ShouldListen"
}

function Get-EffectiveCoreGroups {
  param([Parameter(Mandatory=$true)][string]$Path)
  $text = Get-Content -LiteralPath $Path -Raw
  $lastCompact = $text.LastIndexOf('MetricRows=function({buf}){return <div className="metric-list compact-core-metrics"')
  $lastGrouped = [Math]::Max(
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
  [pscustomobject]@{
    LastCompactMetricRowsIndex = $lastCompact
    LastGroupedMetricRowsIndex = $lastGrouped
    EffectiveCoreGroups = ($lastGrouped -gt $lastCompact)
  }
}

Write-Host "=== BEFORE ==="
$beforeItem = Get-Item -LiteralPath $htmlPath
$beforeHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
$beforeEff = Get-EffectiveCoreGroups -Path $htmlPath
[pscustomobject]@{
  TargetPath = $beforeItem.FullName
  Length = $beforeItem.Length
  LastWriteTime = $beforeItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
  Sha256 = $beforeHash
  ServiceState = (Get-Service -Name $serviceName).Status.ToString()
  Port8093Listening = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768Listening = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  EffectiveCoreGroups = $beforeEff.EffectiveCoreGroups
  LastCompactMetricRowsIndex = $beforeEff.LastCompactMetricRowsIndex
  LastGroupedMetricRowsIndex = $beforeEff.LastGroupedMetricRowsIndex
} | ConvertTo-Json -Depth 4

Write-Host "=== STOP 8093 SERVICE ==="
Stop-Service -Name $serviceName -Force
Wait-PortState -Port 8093 -ShouldListen $false -Seconds 45 | Out-Null
Write-Host "Stopped $serviceName; 8768 listening=$([bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1))"

Write-Host "=== PATCH HTML ==="
& $python -X utf8 $patchScript
if ($LASTEXITCODE -ne 0) {
  throw "patch script failed with exit code $LASTEXITCODE"
}

$afterPatchHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
$afterPatchEff = Get-EffectiveCoreGroups -Path $htmlPath
if (-not $afterPatchEff.EffectiveCoreGroups) {
  throw "patch completed but EffectiveCoreGroups is still false"
}
$afterPatchText = Get-Content -LiteralPath $htmlPath -Raw
if ($afterPatchText -notlike '*OPS-8093-FURNACE-LAYER-CALLOUTS*' -or $afterPatchText -notlike '*furnace-layer-callouts*') {
  throw "patch completed but furnace layer callouts are missing"
}
if ($afterPatchText -notlike '*OPS-8093-CORE-DENSITY-SPARK-V3*') {
  throw "patch completed but core density spark V3 override is missing"
}
if ($afterPatchText -notlike '*OPS-8093-DIAGNOSIS-NORMAL-GREEN*') {
  throw "patch completed but diagnosis normal-green override is missing"
}
if ($afterPatchText -notlike '*OPS-8093-FURNACE-POINT-ANCHORS-V2*') {
  throw "patch completed but furnace point anchors V2 override is missing"
}
if ($afterPatchText -notlike '*OPS-8093-FURNACE-FOLLOW-ANCHORS-V3*') {
  throw "patch completed but furnace follow anchors V3 override is missing"
}
if ($afterPatchText -notlike '*OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK*') {
  throw "patch completed but CAD tooltip fallback is missing"
}
if ($afterPatchText -notlike '*OPS-8093-CAD-GHOST-BANDS-FIX*') {
  throw "patch completed but CAD ghost bands fix is missing"
}
if ($afterPatchText -notlike '*OPS-8093-OVERVIEW-LARGE-TREND-V8*' -or $afterPatchText -notlike '*OverviewTab=function BFOverviewTabLargeTrendV8*' -or $afterPatchText -notlike '*overview-large-trend-grid-v8*') {
  throw "patch completed but overview large trend V8 layout is missing"
}
if ($afterPatchText -notlike '*OPS-8093-OVERVIEW-DECISION-HUB-V11*' -or $afterPatchText -notlike '*OverviewRight=function BFOverviewRightDecisionHubV11*' -or $afterPatchText -notlike '*overview-right-v11*') {
  throw "patch completed but overview decision hub V11 is missing"
}
if ($afterPatchText -notlike '*OPS-8093-AUTO-MONITOR-DOCK-MD-V9*' -or $afterPatchText -notlike '*bf-auto-summary.bf-auto-md*' -or $afterPatchText -notlike '*bf-auto-trigger*') {
  throw "patch completed but auto monitor dock/markdown V9 is missing"
}
if ($afterPatchText -notlike '*OPS-8093-CORE-SPARK-GAP-V10*' -or $afterPatchText -notlike '*ops-core-spark-gap-v10*') {
  throw "patch completed but core spark gap V10 is missing"
}
if ($afterPatchText -notlike '*OPS-8093-CORE-TWO-PAGE-V7*' -or $afterPatchText -notlike '*OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX*' -or $afterPatchText -notlike '*MetricRows=function BFCoreMetricRowsV7*' -or $afterPatchText -notlike '*core-page-v7*' -or $afterPatchText -notlike '*CORE_SPARK_MINUTES=30*' -or $afterPatchText -notlike '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*' -or $afterPatchText -notlike '*text-align:left!important*') {
  throw "patch completed but core two-page V7 layout is missing"
}
if ($afterPatchText -notlike '*OPS-8093-OPTIMIZATION-NOTE-REMOVED*' -or $afterPatchText -like '*<div className="focus-principle">{opt.isNormal?*') {
  throw "patch completed but optimization explanatory note was not removed"
}

Write-Host "=== START 8093 SERVICE ==="
try {
  Start-Service -Name $serviceName
} catch {
  Write-Warning "Start-Service returned an error; waiting for service and port anyway: $($_.Exception.Message)"
}
$port = Wait-PortState -Port 8093 -ShouldListen $true -Seconds 60
Start-Sleep -Seconds 4
$serviceAfterStart = Get-Service -Name $serviceName
if ($serviceAfterStart.Status -ne "Running") {
  throw "$serviceName is not running after start attempt; status=$($serviceAfterStart.Status)"
}

Write-Host "=== VERIFY FILE ==="
& powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript
if ($LASTEXITCODE -ne 0) {
  throw "verify script failed with exit code $LASTEXITCODE"
}

Write-Host "=== VERIFY HTTP ==="
$url = "http://127.0.0.1:8093/?t=deploy-coregroups-20260709#overview"
$response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 45 -Headers @{"Cache-Control"="no-cache"}
$httpText = [string]$response.Content
$httpPath = Join-Path $env:TEMP "8093_http_after_coregroups.html"
[IO.File]::WriteAllText($httpPath, $httpText, [Text.UTF8Encoding]::new($false))
$httpEff = Get-EffectiveCoreGroups -Path $httpPath
if (-not $httpEff.EffectiveCoreGroups) {
  throw "HTTP response still uses compact MetricRows after grouped MetricRows"
}
if ($httpText -notlike '*OPS-8093-FURNACE-LAYER-CALLOUTS*' -or $httpText -notlike '*furnace-layer-callouts*') {
  throw "HTTP response is missing furnace layer callouts"
}
if ($httpText -notlike '*OPS-8093-CORE-DENSITY-SPARK-V3*') {
  throw "HTTP response is missing core density spark V3 override"
}
if ($httpText -notlike '*OPS-8093-DIAGNOSIS-NORMAL-GREEN*') {
  throw "HTTP response is missing diagnosis normal-green override"
}
if ($httpText -notlike '*OPS-8093-FURNACE-POINT-ANCHORS-V2*') {
  throw "HTTP response is missing furnace point anchors V2 override"
}
if ($httpText -notlike '*OPS-8093-FURNACE-FOLLOW-ANCHORS-V3*') {
  throw "HTTP response is missing furnace follow anchors V3 override"
}
if ($httpText -notlike '*OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK*') {
  throw "HTTP response is missing CAD tooltip fallback"
}
if ($httpText -notlike '*OPS-8093-CAD-GHOST-BANDS-FIX*') {
  throw "HTTP response is missing CAD ghost bands fix"
}
if ($httpText -notlike '*OPS-8093-OVERVIEW-LARGE-TREND-V8*' -or $httpText -notlike '*OverviewTab=function BFOverviewTabLargeTrendV8*' -or $httpText -notlike '*overview-large-trend-grid-v8*') {
  throw "HTTP response is missing overview large trend V8 layout"
}
if ($httpText -notlike '*OPS-8093-OVERVIEW-DECISION-HUB-V11*' -or $httpText -notlike '*OverviewRight=function BFOverviewRightDecisionHubV11*' -or $httpText -notlike '*overview-right-v11*') {
  throw "HTTP response is missing overview decision hub V11"
}
if ($httpText -notlike '*OPS-8093-AUTO-MONITOR-DOCK-MD-V9*' -or $httpText -notlike '*bf-auto-summary.bf-auto-md*' -or $httpText -notlike '*bf-auto-trigger*') {
  throw "HTTP response is missing auto monitor dock/markdown V9"
}
if ($httpText -notlike '*OPS-8093-CORE-SPARK-GAP-V10*' -or $httpText -notlike '*ops-core-spark-gap-v10*') {
  throw "HTTP response is missing core spark gap V10"
}
if ($httpText -notlike '*OPS-8093-CORE-TWO-PAGE-V7*' -or $httpText -notlike '*OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX*' -or $httpText -notlike '*MetricRows=function BFCoreMetricRowsV7*' -or $httpText -notlike '*core-page-v7*' -or $httpText -notlike '*CORE_SPARK_MINUTES=30*' -or $httpText -notlike '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*' -or $httpText -notlike '*text-align:left!important*') {
  throw "HTTP response is missing core two-page V7 layout"
}
if ($httpText -notlike '*OPS-8093-OPTIMIZATION-NOTE-REMOVED*' -or $httpText -like '*<div className="focus-principle">{opt.isNormal?*') {
  throw "HTTP response still contains optimization explanatory note"
}

Write-Host "=== AFTER ==="
$afterItem = Get-Item -LiteralPath $htmlPath
[pscustomobject]@{
  TargetPath = $afterItem.FullName
  Length = $afterItem.Length
  LastWriteTime = $afterItem.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
  BeforeSha256 = $beforeHash
  AfterSha256 = $afterPatchHash
  HttpSha256 = (Get-FileHash -LiteralPath $httpPath -Algorithm SHA256).Hash
  ServiceState = (Get-Service -Name $serviceName).Status.ToString()
  Port8093Pid = $port.OwningProcess
  Port8768Listening = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  FileEffectiveCoreGroups = $afterPatchEff.EffectiveCoreGroups
  HttpEffectiveCoreGroups = $httpEff.EffectiveCoreGroups
  FileHasFurnaceLayerCallouts = ($afterPatchText -like '*OPS-8093-FURNACE-LAYER-CALLOUTS*' -and $afterPatchText -like '*furnace-layer-callouts*')
  HttpHasFurnaceLayerCallouts = ($httpText -like '*OPS-8093-FURNACE-LAYER-CALLOUTS*' -and $httpText -like '*furnace-layer-callouts*')
  FileHasCoreDensitySparkV3 = ($afterPatchText -like '*OPS-8093-CORE-DENSITY-SPARK-V3*')
  HttpHasCoreDensitySparkV3 = ($httpText -like '*OPS-8093-CORE-DENSITY-SPARK-V3*')
  FileHasDiagnosisNormalGreen = ($afterPatchText -like '*OPS-8093-DIAGNOSIS-NORMAL-GREEN*')
  HttpHasDiagnosisNormalGreen = ($httpText -like '*OPS-8093-DIAGNOSIS-NORMAL-GREEN*')
  FileHasFurnacePointAnchorsV2 = ($afterPatchText -like '*OPS-8093-FURNACE-POINT-ANCHORS-V2*')
  HttpHasFurnacePointAnchorsV2 = ($httpText -like '*OPS-8093-FURNACE-POINT-ANCHORS-V2*')
  FileHasFurnaceFollowAnchorsV3 = ($afterPatchText -like '*OPS-8093-FURNACE-FOLLOW-ANCHORS-V3*')
  HttpHasFurnaceFollowAnchorsV3 = ($httpText -like '*OPS-8093-FURNACE-FOLLOW-ANCHORS-V3*')
  FileHasCadTooltipFallback = ($afterPatchText -like '*OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK*')
  HttpHasCadTooltipFallback = ($httpText -like '*OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK*')
  FileHasCadGhostBandsFix = ($afterPatchText -like '*OPS-8093-CAD-GHOST-BANDS-FIX*')
  HttpHasCadGhostBandsFix = ($httpText -like '*OPS-8093-CAD-GHOST-BANDS-FIX*')
  FileHasOverviewLargeTrendV8 = ($afterPatchText -like '*OPS-8093-OVERVIEW-LARGE-TREND-V8*' -and $afterPatchText -like '*overview-large-trend-grid-v8*')
  HttpHasOverviewLargeTrendV8 = ($httpText -like '*OPS-8093-OVERVIEW-LARGE-TREND-V8*' -and $httpText -like '*overview-large-trend-grid-v8*')
  FileHasOverviewDecisionHubV11 = ($afterPatchText -like '*OPS-8093-OVERVIEW-DECISION-HUB-V11*' -and $afterPatchText -like '*overview-right-v11*')
  HttpHasOverviewDecisionHubV11 = ($httpText -like '*OPS-8093-OVERVIEW-DECISION-HUB-V11*' -and $httpText -like '*overview-right-v11*')
  FileHasAutoMonitorDockMdV9 = ($afterPatchText -like '*OPS-8093-AUTO-MONITOR-DOCK-MD-V9*' -and $afterPatchText -like '*bf-auto-summary.bf-auto-md*')
  HttpHasAutoMonitorDockMdV9 = ($httpText -like '*OPS-8093-AUTO-MONITOR-DOCK-MD-V9*' -and $httpText -like '*bf-auto-summary.bf-auto-md*')
  FileHasCoreSparkGapV10 = ($afterPatchText -like '*OPS-8093-CORE-SPARK-GAP-V10*' -and $afterPatchText -like '*ops-core-spark-gap-v10*')
  HttpHasCoreSparkGapV10 = ($httpText -like '*OPS-8093-CORE-SPARK-GAP-V10*' -and $httpText -like '*ops-core-spark-gap-v10*')
  FileHasCoreTwoColumnV4 = ($afterPatchText -like '*OPS-8093-CORE-TWO-COLUMN-V4*' -and $afterPatchText -like '*core-two-column-v4*')
  HttpHasCoreTwoColumnV4 = ($httpText -like '*OPS-8093-CORE-TWO-COLUMN-V4*' -and $httpText -like '*core-two-column-v4*')
  FileHasBalancedCoreColumns = ($afterPatchText -like '*OPS-8093-CORE-TWO-COLUMN-V4-BALANCED-14-14*')
  HttpHasBalancedCoreColumns = ($httpText -like '*OPS-8093-CORE-TWO-COLUMN-V4-BALANCED-14-14*')
  FileHasCoreTwoColumnFillLargeV5 = ($afterPatchText -like '*OPS-8093-CORE-TWO-COLUMN-V5-FILL-LARGE*')
  HttpHasCoreTwoColumnFillLargeV5 = ($httpText -like '*OPS-8093-CORE-TWO-COLUMN-V5-FILL-LARGE*')
  FileHasCoreValueAlignV6 = ($afterPatchText -like '*OPS-8093-CORE-VALUE-ALIGN-V6*' -and $afterPatchText -like '*font-variant-numeric:tabular-nums!important*' -and $afterPatchText -like '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*')
  HttpHasCoreValueAlignV6 = ($httpText -like '*OPS-8093-CORE-VALUE-ALIGN-V6*' -and $httpText -like '*font-variant-numeric:tabular-nums!important*' -and $httpText -like '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*')
  FileHasCoreTwoPageV7 = ($afterPatchText -like '*OPS-8093-CORE-TWO-PAGE-V7*' -and $afterPatchText -like '*MetricRows=function BFCoreMetricRowsV7*' -and $afterPatchText -like '*core-page-v7*')
  HttpHasCoreTwoPageV7 = ($httpText -like '*OPS-8093-CORE-TWO-PAGE-V7*' -and $httpText -like '*MetricRows=function BFCoreMetricRowsV7*' -and $httpText -like '*core-page-v7*')
  FileHasCoreValueDDIN = ($afterPatchText -like '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*')
  HttpHasCoreValueDDIN = ($httpText -like '*font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important*')
  FileHasCoreTwoPageV7SpecificityFix = ($afterPatchText -like '*OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX*' -and $afterPatchText -like '*text-align:left!important*')
  HttpHasCoreTwoPageV7SpecificityFix = ($httpText -like '*OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX*' -and $httpText -like '*text-align:left!important*')
  FileHasOptimizationNoteRemoved = ($afterPatchText -like '*OPS-8093-OPTIMIZATION-NOTE-REMOVED*' -and $afterPatchText -notlike '*正常炉况不生成满屏操作建议*')
  HttpHasOptimizationNoteRemoved = ($httpText -like '*OPS-8093-OPTIMIZATION-NOTE-REMOVED*' -and $httpText -notlike '*正常炉况不生成满屏操作建议*')
  FileLastCompactMetricRowsIndex = $afterPatchEff.LastCompactMetricRowsIndex
  FileLastGroupedMetricRowsIndex = $afterPatchEff.LastGroupedMetricRowsIndex
  HttpLastCompactMetricRowsIndex = $httpEff.LastCompactMetricRowsIndex
  HttpLastGroupedMetricRowsIndex = $httpEff.LastGroupedMetricRowsIndex
} | ConvertTo-Json -Depth 4
