$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$body = @{
    message = "请用一句话回答：当前模型服务是否在线？"
    stream = $false
} | ConvertTo-Json -Compress

$sw = [Diagnostics.Stopwatch]::StartNew()
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/qa/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 120
$sw.Stop()

Write-Host ("elapsed_ms=" + [int]$sw.ElapsedMilliseconds)
$response.Content
& "F:\Ollama\ollama.exe" ps
