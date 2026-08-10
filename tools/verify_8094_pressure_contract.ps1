$ErrorActionPreference = 'Stop'
$root = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/' -TimeoutSec 30
$latest = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/api/furnace-rules/latest' -TimeoutSec 30
$json = $latest.Content | ConvertFrom-Json
$page = $root.Content
$sensitive = @('formula','weights','thresholds','normalized_value','contribution','feature_key','g_H','g_L','g_A')
$leak = @($sensitive | Where-Object { $latest.Content.Contains($_) })
$counts = @{}
foreach ($rule in @($json.rules)) {
    $cat = [string]$rule.category
    if (-not $counts.ContainsKey($cat)) { $counts[$cat] = 0 }
    $counts[$cat]++
}
[pscustomobject]@{
    http8094 = [int]$root.StatusCode
    latestStatus = [int]$latest.StatusCode
    ruleCount = @($json.rules).Count
    categoryCounts = $counts
    schemaVersion = $json.schema_version
    pageHasAbcAsset = $page.Contains('abc-furnace-rules-production')
    publicApiSensitiveFields = $leak
    ok = ([int]$root.StatusCode -eq 200 -and [int]$latest.StatusCode -eq 200 -and @($json.rules).Count -eq 33 -and $leak.Count -eq 0)
} | ConvertTo-Json -Depth 5
