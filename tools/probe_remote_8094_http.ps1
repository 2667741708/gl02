$ErrorActionPreference = "Stop"
$connection = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $connection) { throw "8094 not listening" }
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 30
[ordered]@{ pid = $connection.OwningProcess; http = [int]$response.StatusCode } | ConvertTo-Json -Compress
