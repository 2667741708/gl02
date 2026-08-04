$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$python = 'C:\Program Files\Python311\python.exe'
$backend = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$mcp = Join-Path $root '高炉前端数据\智能助手\mcp\bf_data_mcp_server.py'
$stageBackend = Join-Path $root 'logs\ollama_proxy_server.mcp_colloquial_fix_20260715.staged.py'
$stageMcp = Join-Path $root 'logs\bf_data_mcp_server.mcp_colloquial_fix_20260715.staged.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backendBackup = "$backend.bak_mcp_colloquial_fix_$stamp"
$mcpBackup = "$mcp.bak_mcp_colloquial_fix_$stamp"
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
foreach ($marker in @(
  'QA_MCP_DIRECT_TOOL_TERMS',
  'def qa_mcp_exact_variables',
  'def qa_mcp_group_variables',
  'P_top_gas_A',
  'L_south',
  'direct_tool_intent'
)) {
  if (-not $backendText.Contains($marker)) { throw "Staged backend missing marker: $marker" }
}
$mcpText = Get-Content -LiteralPath $stageMcp -Raw -Encoding UTF8
if (-not $mcpText.Contains('L_south、L_north、P_top_gas_A-D')) {
  throw 'Staged MCP file is missing the specific-variable tool guidance.'
}

& $python -m py_compile $stageBackend $stageMcp
if ($LASTEXITCODE -ne 0) { throw "Remote py_compile failed: $LASTEXITCODE" }
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
