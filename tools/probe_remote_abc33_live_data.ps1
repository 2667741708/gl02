$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8094/api/furnace-rules/latest?cb=live-data-r1" -TimeoutSec 45
$rules = @($response.rules)
$statusCounts = @{}
foreach ($group in ($rules | Group-Object status)) {
    $statusCounts[$group.Name] = $group.Count
}
$positiveConfidence = @($rules | Where-Object { [double]$_.confidence -gt 0 })
$computable = @($rules | Where-Object { $_.score_available -eq $true })
$samples = @($rules | Sort-Object { [double]$_.confidence } -Descending | Select-Object -First 8 rule_id,category,status,score,score_available,confidence,missing_sensors)
[ordered]@{
    ok = $response.ok
    evaluation_id = $response.evaluation_id
    evaluation_ts = $response.evaluation_ts
    rules = $rules.Count
    alerts = @($response.alerts).Count
    status_counts = $statusCounts
    positive_confidence = $positiveConfidence.Count
    computable = $computable.Count
    samples = $samples
} | ConvertTo-Json -Depth 8
