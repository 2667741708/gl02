$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$python = 'C:\Program Files\Python311\python.exe'
$backend = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$mcp = Join-Path $root '高炉前端数据\智能助手\mcp\bf_data_mcp_server.py'
$extension = Join-Path $root '高炉前端数据\智能助手\mcp\gl02_static_pressure_points.json'
$helper = Join-Path $root '高炉前端数据\智能助手\mcp\gl02_pspace_direct_query.py'
$stageBackend = Join-Path $root 'logs\ollama_proxy_server.static_pressure_af_20260716.staged.py'
$stageMcp = Join-Path $root 'logs\bf_data_mcp_server.static_pressure_af_20260716.staged.py'
$stageExtension = Join-Path $root 'logs\gl02_static_pressure_points.20260716.staged.json'
$stageHelper = Join-Path $root 'logs\gl02_pspace_direct_query.static_pressure_af_20260716.staged.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backups = @{}
$hadExtension = Test-Path -LiteralPath $extension

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
  Start-Service -Name $service -ErrorAction SilentlyContinue
  Wait-Port 8093 $true
}

foreach ($path in @($stageBackend, $stageMcp, $stageExtension, $stageHelper, $backend, $mcp, $helper, $python)) {
  if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}
if (-not (Get-Content -LiteralPath $stageBackend -Raw -Encoding UTF8).Contains('P_static_{level}_{position}')) { throw 'Backend marker missing.' }
if (-not (Get-Content -LiteralPath $stageMcp -Raw -Encoding UTF8).Contains('STATIC_PRESSURE_EXTENSION')) { throw 'MCP marker missing.' }
$catalog = Get-Content -LiteralPath $stageExtension -Raw -Encoding UTF8 | ConvertFrom-Json
if (@($catalog.variables).Count -ne 18) { throw 'Static-pressure extension must contain exactly 18 variables.' }
& $python -m py_compile $stageBackend $stageMcp $stageHelper
if ($LASTEXITCODE -ne 0) { throw 'Remote py_compile failed.' }
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) { throw '8768 is not listening.' }

foreach ($item in @(@($backend, "$backend.bak_static_pressure_af_$stamp"), @($mcp, "$mcp.bak_static_pressure_af_$stamp"), @($helper, "$helper.bak_static_pressure_af_$stamp"))) {
  Copy-Item -LiteralPath $item[0] -Destination $item[1] -Force
  $backups[$item[0]] = $item[1]
}
if ($hadExtension) {
  $extensionBackup = "$extension.bak_static_pressure_af_$stamp"
  Copy-Item -LiteralPath $extension -Destination $extensionBackup -Force
  $backups[$extension] = $extensionBackup
}

try {
  Stop-Service -Name $service -Force
  Wait-Port 8093 $false
  Copy-Item -LiteralPath $stageBackend -Destination $backend -Force
  Copy-Item -LiteralPath $stageMcp -Destination $mcp -Force
  Copy-Item -LiteralPath $stageExtension -Destination $extension -Force
  Copy-Item -LiteralPath $stageHelper -Destination $helper -Force
  & $python -m py_compile $backend $mcp $helper
  if ($LASTEXITCODE -ne 0) { throw 'Deployed py_compile failed.' }
  Start-ProxyService
  Start-Sleep -Seconds 4
  $response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp" -UseBasicParsing -TimeoutSec 45
  if ([int]$response.StatusCode -ne 200) { throw "8093 HTTP status is $($response.StatusCode)" }
} catch {
  $deployError = $_
  Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
  Wait-Port 8093 $false
  foreach ($path in @($backend, $mcp, $helper)) { Copy-Item -LiteralPath $backups[$path] -Destination $path -Force }
  if ($hadExtension) { Copy-Item -LiteralPath $backups[$extension] -Destination $extension -Force }
  else { Remove-Item -LiteralPath $extension -Force -ErrorAction SilentlyContinue }
  Start-ProxyService
  throw $deployError
}

[pscustomobject]@{
  Stamp = $stamp
  BackendBackup = $backups[$backend]
  McpBackup = $backups[$mcp]
  HelperBackup = $backups[$helper]
  ExtensionBackup = if ($hadExtension) { $backups[$extension] } else { $null }
  BackendSha256 = (Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash
  McpSha256 = (Get-FileHash -LiteralPath $mcp -Algorithm SHA256).Hash
  HelperSha256 = (Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash
  ExtensionSha256 = (Get-FileHash -LiteralPath $extension -Algorithm SHA256).Hash
  ExtensionVariables = @($catalog.variables).Count
  Service = (Get-Service -Name $service).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HttpStatus = [int]$response.StatusCode
} | ConvertTo-Json -Depth 3
