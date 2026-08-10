$ErrorActionPreference = "Stop"
$data = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/api/furnace-rules/latest" -TimeoutSec 20).Content | ConvertFrom-Json
if (-not $data.ok -or @($data.rules).Count -ne 33) { throw "expected 33 public rules" }
$counts = @{
    A = @($data.rules | Where-Object category -eq 'A').Count
    B = @($data.rules | Where-Object category -eq 'B').Count
    C = @($data.rules | Where-Object category -eq 'C').Count
}
if ($counts.A -ne 9 -or $counts.B -ne 13 -or $counts.C -ne 11) { throw "A/B/C counts mismatch" }
[ordered]@{ ok=$true; ruleCount=@($data.rules).Count; categoryCounts=$counts; alertCount=@($data.alerts).Count; schemaVersion=$data.schema_version } | ConvertTo-Json -Depth 5
