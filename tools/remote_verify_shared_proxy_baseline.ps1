$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$proxy = Join-Path $root "高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$page = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop | Select-Object -First 1
$service = Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction Stop
$http = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/api/ollama/status" -TimeoutSec 30
[ordered]@{
    proxySha256 = (Get-FileHash -LiteralPath $proxy -Algorithm SHA256).Hash
    proxyLength = (Get-Item -LiteralPath $proxy).Length
    proxyLastWriteTime = (Get-Item -LiteralPath $proxy).LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    pageSha256 = (Get-FileHash -LiteralPath $page -Algorithm SHA256).Hash
    serviceStatus = [string]$service.Status
    listenerPid = [int]$listener.OwningProcess
    httpStatus = [int]$http.StatusCode
} | ConvertTo-Json -Depth 4
