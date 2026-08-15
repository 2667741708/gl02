$ErrorActionPreference = 'Stop'
$rows = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -ge 8000 -and $_.LocalPort -le 9000 } |
  Sort-Object LocalPort -Unique |
  ForEach-Object {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" -ErrorAction SilentlyContinue
    [ordered]@{ port = [int]$_.LocalPort; pid = [int]$_.OwningProcess; process = $proc.Name; command = $proc.CommandLine }
  }
$http = [ordered]@{}
foreach ($port in @(8092,8093,8094,8096,8891,8892)) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/?curve_inventory=20260811" -TimeoutSec 8
    $body = $response.Content
    $http[[string]$port] = [ordered]@{ status = [int]$response.StatusCode; bytes = $body.Length; curve = $body -match '(?i)echarts|canvas|trend|curve|temperature|sensor' }
  } catch { $http[[string]$port] = [ordered]@{ status = $null; error = $_.Exception.Message } }
}
[ordered]@{ listeners = @($rows); http = $http } | ConvertTo-Json -Depth 8
