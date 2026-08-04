$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$target = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$patcher = Join-Path $root "tools\patch_core_iqr_thresholds_20260715.py"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = "$target.bak_core_iqr_thresholds_$stamp"

if (-not (Test-Path -LiteralPath $target)) { throw "Target HTML not found: $target" }
if (-not (Test-Path -LiteralPath $patcher)) { throw "Patcher not found: $patcher" }

Copy-Item -LiteralPath $target -Destination $backup
& "C:\Program Files\Python311\python.exe" $patcher $target
if ($LASTEXITCODE -ne 0) { throw "Threshold patch failed" }

$html = Get-Content -LiteralPath $target -Raw -Encoding UTF8
$checks = [ordered]@{
    Marker = $html.Contains("REQ-CORE-IQR-BANDS-NEG1-POS1-20260715")
    CoreHigh = $html.Contains("if(z>1)return{label:'偏高'")
    CoreLow = $html.Contains("if(z<-1)return{label:'偏低'")
    BaselineBand = $html.Contains(":a>1?{label:z>0?'偏高':'偏低'")
    OldCoreHighAbsent = -not $html.Contains("if(z>0.5)return{label:'偏高'")
    OldCoreLowAbsent = -not $html.Contains("if(z<-0.5)return{label:'偏低'")
}
if ($checks.Values -contains $false) { throw "File verification failed: $($checks | ConvertTo-Json -Compress)" }

Restart-Service -Name "BFV4PreviewProxy8093" -Force
Start-Sleep -Seconds 8
$service = Get-Service -Name "BFV4PreviewProxy8093"
$listen8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue)
$listen8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
$response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -Uri "http://127.0.0.1:8093/?t=core-iqr-$stamp"
$httpChecks = [ordered]@{
    Marker = $response.Content.Contains("REQ-CORE-IQR-BANDS-NEG1-POS1-20260715")
    CoreHigh = $response.Content.Contains("if(z>1)return{label:'偏高'")
    CoreLow = $response.Content.Contains("if(z<-1)return{label:'偏低'")
    BaselineBand = $response.Content.Contains(":a>1?{label:z>0?'偏高':'偏低'")
}
if ($service.Status -ne "Running" -or -not $listen8093 -or -not $listen8768 -or $response.StatusCode -ne 200 -or $httpChecks.Values -contains $false) {
    throw "Runtime verification failed"
}

[ordered]@{
    Backup = $backup
    Service = [string]$service.Status
    Listen8093 = $listen8093
    Listen8768 = $listen8768
    HttpStatus = $response.StatusCode
    FileChecks = $checks
    HttpChecks = $httpChecks
    Sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 4
