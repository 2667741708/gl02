$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $pidValue = [int]$listener.OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
    Write-Host "=== 8093 process ==="
    [pscustomobject]@{
        pid = $pidValue
        command = $proc.CommandLine
        creation = $proc.CreationDate
    } | ConvertTo-Json -Depth 3
}

Write-Host "=== 8093 pgvector status ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/status" -TimeoutSec 30).Content
} catch {
    Write-Host ("status_error=" + $_.Exception.Message)
}

Write-Host "=== 8093 sample knowledge search ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=%E7%82%89%E5%87%89&top_k=3" -TimeoutSec 30).Content
} catch {
    Write-Host ("search_error=" + $_.Exception.Message)
}
