$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$python = 'C:\Program Files\Python311\python.exe'
$backend = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$mcp = Join-Path $root '高炉前端数据\智能助手\mcp\bf_data_mcp_server.py'
$stageBackend = Join-Path $root 'logs\ollama_proxy_server.body_temperature_matrix_20260715.staged.py'
$stageMcp = Join-Path $root 'logs\bf_data_mcp_server.body_temperature_matrix_20260715.staged.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backendBackup = "$backend.bak_body_temperature_matrix_$stamp"
$mcpBackup = "$mcp.bak_body_temperature_matrix_$stamp"
$deployed = $false

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 90) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

function Start-ProxyService {
  try {
    Start-Service -Name $service -ErrorAction Stop
  } catch {
    Start-Sleep -Seconds 4
    if ((Get-Service -Name $service).Status -ne 'Running') { throw }
  }
  Wait-Port 8093 $true
}

foreach ($path in @($stageBackend, $stageMcp, $backend, $mcp, $python)) {
  if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}

$backendText = Get-Content -LiteralPath $stageBackend -Raw -Encoding UTF8
foreach ($marker in @('plot_gl02_body_temperature_matrix', 'query_gl02_sensors', 'qa_mcp_catalog_variables', 'qa_mcp_body_temperature_variables', 'MCP数据图')) {
  if (-not $backendText.Contains($marker)) { throw "Staged backend missing marker: $marker" }
}
$mcpText = Get-Content -LiteralPath $stageMcp -Raw -Encoding UTF8
foreach ($marker in @('def normalize_body_temperature_positions', 'def render_body_temperature_matrix', 'def plot_gl02_body_temperature_matrix', 'def query_gl02_sensors', 'current_value_p05_p95')) {
  if (-not $mcpText.Contains($marker)) { throw "Staged MCP file missing marker: $marker" }
}

& $python -m py_compile $stageBackend $stageMcp
if ($LASTEXITCODE -ne 0) { throw "Remote py_compile failed: $LASTEXITCODE" }
& $python -c "import matplotlib; print(matplotlib.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Remote matplotlib import failed.' }
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
  throw '8768 is not listening; refusing deployment.'
}

$beforeBackendHash = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
$beforeMcpHash = (Get-FileHash -LiteralPath $mcp -Algorithm SHA256).Hash
Copy-Item -LiteralPath $backend -Destination $backendBackup -Force
Copy-Item -LiteralPath $mcp -Destination $mcpBackup -Force

try {
  Stop-Service -Name $service -Force
  Wait-Port 8093 $false
  Copy-Item -LiteralPath $stageBackend -Destination $backend -Force
  Copy-Item -LiteralPath $stageMcp -Destination $mcp -Force
  & $python -m py_compile $backend $mcp
  if ($LASTEXITCODE -ne 0) { throw "Deployed py_compile failed: $LASTEXITCODE" }
  $deployed = $true
  Start-ProxyService
  Start-Sleep -Seconds 4
  $response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp" -UseBasicParsing -TimeoutSec 45
  if ([int]$response.StatusCode -ne 200) { throw "8093 HTTP status is $($response.StatusCode)" }
} catch {
  $deployError = $_
  if ($deployed) {
    Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
    Wait-Port 8093 $false
    Copy-Item -LiteralPath $backendBackup -Destination $backend -Force
    Copy-Item -LiteralPath $mcpBackup -Destination $mcp -Force
  }
  Start-ProxyService
  throw $deployError
}

[pscustomobject]@{
  BackupBackend = $backendBackup
  BackupMcp = $mcpBackup
  BeforeBackendHash = $beforeBackendHash
  AfterBackendHash = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
  BeforeMcpHash = $beforeMcpHash
  AfterMcpHash = (Get-FileHash -LiteralPath $mcp -Algorithm SHA256).Hash
  Service = (Get-Service -Name $service).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HttpStatus = [int]$response.StatusCode
} | ConvertTo-Json -Depth 3
