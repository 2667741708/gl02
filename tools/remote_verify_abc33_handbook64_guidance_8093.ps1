$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$version = 'abc33-20260810-handbook64-guidance-r1'
$listeners = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) { throw "port not listening: $port" }
    $listeners["p$port"] = [int]$listener.OwningProcess
}

$page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$version#optimization" -TimeoutSec 60
$asset = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 60
$latest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest' -TimeoutSec 60
$detail = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/A1/detail' -TimeoutSec 60

if ($page.StatusCode -ne 200 -or -not $page.Content.Contains("?v=$version")) { throw 'page version mismatch' }
foreach ($marker in '炉况形成原理', '五步干预处置流程', 'abc33-guidance') {
    if (-not $asset.Content.Contains($marker)) { throw "asset marker missing: $marker" }
}
if ([int]$latest.rules.Count -ne 33) { throw "latest API returned $($latest.rules.Count) rules" }
if ($latest.catalog_version -ne 'abc33-catalog.v3.handbook64-guidance') {
    throw "catalog version is still $($latest.catalog_version)"
}
$rule = $detail.detail
if (-not $rule.principle -or $rule.principle.Length -lt 20) { throw 'A1 principle is missing' }
if ([int]$rule.intervention_order.Count -ne 5) { throw 'A1 intervention step count is not five' }
if ([int]$rule.source_refs.Count -lt 1) { throw 'A1 source references are missing' }
$json = $detail | ConvertTo-Json -Depth 30 -Compress
foreach ($forbidden in 'formula_terms', 'normalized_value', 'contribution', 'feature_key', 'thresholds', 'weights') {
    if ($json.Contains($forbidden)) { throw "public contract leaked: $forbidden" }
}

[ordered]@{
    ok = $true
    checked_at = (Get-Date).ToString('o')
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
        BFV4PreviewWs8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    }
    listeners = $listeners
    http8093 = [int]$page.StatusCode
    rule_count = [int]$latest.rules.Count
    catalog_version = $latest.catalog_version
    evaluation_ts = $latest.evaluation_ts
    a1 = [ordered]@{
        status = $rule.status
        score = $rule.score
        principle = $rule.principle
        intervention_steps = $rule.intervention_order
        source_refs = $rule.source_refs
    }
}|ConvertTo-Json -Depth 10
