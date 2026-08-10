$services = Get-Service -Name BFV4PreviewProxy8093,BFV4PreviewProxy8093HealthCheck -ErrorAction SilentlyContinue
$services | Select-Object Name,Status
$listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue
$listener | Select-Object LocalAddress,LocalPort,OwningProcess
try {
  $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 'http://127.0.0.1:8093/api/ollama/status'
  Write-Output ("http_status=" + $response.StatusCode)
} catch {
  Write-Output 'http_status=error'
}
