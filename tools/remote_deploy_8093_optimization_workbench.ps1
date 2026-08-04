$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$serviceName = "BFV4PreviewProxy8093"
$htmlPath = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$stagedPath = Join-Path $root "logs\frontend_dashboard_v3.optimization_workbench.staged.html"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$htmlPath.bak_optimization_workbench_$stamp"

function Wait-Port {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 45)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

if (-not (Test-Path -LiteralPath $htmlPath)) { throw "Target HTML missing: $htmlPath" }
if (-not (Test-Path -LiteralPath $stagedPath)) { throw "Staged HTML missing: $stagedPath" }

$stagedText = Get-Content -LiteralPath $stagedPath -Raw -Encoding UTF8
$required = @(
    'optimization-workbench-v10',
    'BFOptimizationWorkbenchV10',
    'OPS-8093-FURNACE-LAYER-CALLOUTS',
    'OPS-8093-OVERVIEW-DECISION-HUB-V11',
    'OPS-8093-AUTO-MONITOR-DOCK-MD-V9',
    '高炉工艺大模型智能决策系统'
)
foreach ($marker in $required) {
    if (-not $stagedText.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}

$before = [pscustomobject]@{
    Service = (Get-Service -Name $serviceName).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Hash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
}

Stop-Service -Name $serviceName -Force
Wait-Port -Port 8093 -Listening $false
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw "8768 data bridge stopped unexpectedly; refusing replacement"
}

Copy-Item -LiteralPath $htmlPath -Destination $backupPath
Copy-Item -LiteralPath $stagedPath -Destination $htmlPath -Force

Start-Service -Name $serviceName
Wait-Port -Port 8093 -Listening $true
Start-Sleep -Seconds 4

$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?t=$stamp#optimization" -UseBasicParsing -TimeoutSec 45
$httpText = $response.Content
foreach ($marker in $required) {
    if (-not $httpText.Contains($marker)) { throw "HTTP response missing marker: $marker" }
}

[pscustomobject]@{
    Before = $before
    BackupPath = $backupPath
    AfterService = (Get-Service -Name $serviceName).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    FileHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
    HttpStatus = [int]$response.StatusCode
    HasOptimizationWorkbench = $httpText.Contains('optimization-workbench-v10')
    HasFormalHeader = $httpText.Contains('topbar branded-topbar')
} | ConvertTo-Json -Depth 4
