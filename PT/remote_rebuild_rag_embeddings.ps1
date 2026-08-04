$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== ollama tags ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 30).Content
} catch {
    "tags_error=" + $_.Exception.Message
}

Write-Host "=== pgvector status before rebuild ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/status" -TimeoutSec 30).Content
} catch {
    "status_error=" + $_.Exception.Message
}

Write-Host "=== rebuild embeddings ==="
try {
    $body = @{ force = $true } | ConvertTo-Json -Compress
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/rebuild" -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 900).Content
} catch {
    "rebuild_error=" + $_.Exception.Message
}

Write-Host "=== pgvector status after rebuild ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/pgvector/status" -TimeoutSec 30).Content
} catch {
    "status_error=" + $_.Exception.Message
}

Write-Host "=== vector search sample ==="
try {
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/knowledge/vector/search?q=%E7%82%89%E5%87%89&top_k=3" -TimeoutSec 60).Content
} catch {
    "vector_search_error=" + $_.Exception.Message
}

Write-Host "=== warm diagnosis model ==="
try {
    $warm = @{
        model = "bf-diagnosis-runtime:v1"
        stream = $false
        keep_alive = "24h"
        messages = @(@{ role = "user"; content = "ping" })
        options = @{ num_predict = 1; temperature = 0 }
    } | ConvertTo-Json -Depth 8 -Compress
    (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $warm -TimeoutSec 180).Content
} catch {
    "warm_error=" + $_.Exception.Message
}

Write-Host "=== ollama ps ==="
& "F:\Ollama\ollama.exe" ps
