$ErrorActionPreference = "Stop"
$ollama = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 10
$status = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8095/api/ollama/status" -TimeoutSec 20
$body = @{
    messages = @(@{ role = "user"; content = "Reply with exactly: 8095 dynamic model link OK" })
    stream = $false
    think = $false
    options = @{ num_predict = 40; temperature = 0 }
} | ConvertTo-Json -Depth 8 -Compress
$chat = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8095/v1/chat/completions" -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 180
$page = Invoke-WebRequest -Method Get -Uri "http://127.0.0.1:8095/?ws_port=8767" -TimeoutSec 20
[ordered]@{
    resident_models = @($ollama.models | ForEach-Object { $_.name })
    status_ok = $status.ok
    status_proxy_ok = $status.proxy_ok
    status_ollama_ok = $status.ollama_ok
    status_model_ok = $status.model_ok
    status_target = $status.target_model
    chat_response = $chat.choices[0].message.content
    page_status = [int]$page.StatusCode
    page_has_title = $page.Content.Contains("高炉工艺大模型智能决策系统")
} | ConvertTo-Json -Depth 8
