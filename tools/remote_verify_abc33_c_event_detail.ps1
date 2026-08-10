$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$ports=8093,8094,8768,8770,11434
$listeners=@{}
foreach($port in $ports){
  $item=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1
  if(-not$item){throw "port not listening: $port"}
  $listeners["p$port"]=[int]$item.OwningProcess
}
$result=[ordered]@{checked_at=(Get-Date).ToString('o');listeners=$listeners;services=@{};pages=@{}}
$result.services.BFV4PreviewWs8768=(Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
$result.services.BFV4PreviewProxy8093=(Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
foreach($port in 8093,8094){
  $latest=Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/furnace-rules/latest" -TimeoutSec 60
  $detail=Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/furnace-rules/C7/detail" -TimeoutSec 60
  $page=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/?cb=abc33-20260810-c-event-detail-r3#optimization" -TimeoutSec 60
  $json=$latest|ConvertTo-Json -Depth 20 -Compress
  foreach($secret in 'raw_formula_score','event_confirmation_sources','formula_terms','normalized_value','contribution','feature_key'){
    if($json.Contains($secret)){throw "public contract leaked $secret on $port"}
  }
  $rules=@{}
  foreach($ruleId in 'C4','C5','C7'){
    $item=$latest.rules|Where-Object rule_id -eq $ruleId|Select-Object -First 1
    if(-not$item){throw "missing $ruleId on $port"}
    $rules[$ruleId]=[ordered]@{score=$item.score;status=$item.status;confirmation=$item.event_confirmation_state;summary=$item.event_confirmation_summary}
  }
  if($detail.schema_version-ne'furnace_rule_detail.v2'){throw "unexpected detail schema on $port"}
  if([int]$detail.sensor_review.body_metrics.Count-ne80){throw "body metric count mismatch on $port"}
  if([int]$detail.sensor_review.metric_count-lt100){throw "review metric count mismatch on $port"}
  if(-not$page.Content.Contains('abc33-20260810-c-event-detail-r3')){throw "page version mismatch on $port"}
  $first=$detail.sensor_review.main_metrics|Select-Object -First 1
  $result.pages["p$port"]=[ordered]@{
    http_status=[int]$page.StatusCode;rule_count=[int]$latest.rules.Count;detail_schema=$detail.schema_version
    metric_count=[int]$detail.sensor_review.metric_count;body_count=[int]$detail.sensor_review.body_metrics.Count
    cooling_count=[int]$detail.sensor_review.cooling_metrics.Count;missing_count=[int]$detail.sensor_review.missing_count
    rules=$rules
    first_review=[ordered]@{label=$first.label;current=$first.current_value;baseline=$first.baseline.median;delta15=$first.changes.'15';delta30=$first.changes.'30';delta60=$first.changes.'60';semantic=$first.semantic_summary}
  }
}
$result|ConvertTo-Json -Depth 10
