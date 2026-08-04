$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$serviceName = "BFV4PreviewProxy8093"
$htmlPath = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$htmlPath.bak_baseline_title_$stamp"
$oldTitle = "基线对比（当前值对比历史基线）"
$newTitle = "基线对比"

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

if (-not (Test-Path -LiteralPath $htmlPath)) {
    throw "8093 preview HTML not found: $htmlPath"
}

$before = [pscustomobject]@{
    Service = (Get-Service -Name $serviceName).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Hash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
}

$text = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8
$hadOldTitle = $text.Contains($oldTitle)
$newCountBefore = ([regex]::Matches($text, [regex]::Escape('Panel title="基线对比"'))).Count

if ($hadOldTitle) {
    Stop-Service -Name $serviceName -Force
    Wait-Port -Port 8093 -Listening $false
    if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8768 data bridge stopped unexpectedly; refusing replacement"
    }

    Copy-Item -LiteralPath $htmlPath -Destination $backupPath
    $text = $text.Replace($oldTitle, $newTitle)
    [IO.File]::WriteAllText($htmlPath, $text, [Text.UTF8Encoding]::new($false))

    Start-Service -Name $serviceName
    Wait-Port -Port 8093 -Listening $true
    Start-Sleep -Seconds 4
}

$afterText = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8
if ($afterText.Contains($oldTitle)) {
    throw "File still contains old baseline title"
}
if (-not $afterText.Contains('Panel title="基线对比"')) {
    throw "File missing new baseline title"
}

$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?t=baseline-title-$stamp#diagnosis" -UseBasicParsing -TimeoutSec 45
$httpText = $response.Content
if ($httpText.Contains($oldTitle)) {
    throw "HTTP response still contains old baseline title"
}
if (-not $httpText.Contains('Panel title="基线对比"')) {
    throw "HTTP response missing new baseline title"
}

[pscustomobject]@{
    Before = $before
    Changed = $hadOldTitle
    BackupPath = $(if ($hadOldTitle) { $backupPath } else { $null })
    NewTitleCountBefore = $newCountBefore
    NewTitleCountAfter = ([regex]::Matches($afterText, [regex]::Escape('Panel title="基线对比"'))).Count
    AfterService = (Get-Service -Name $serviceName).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    FileHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
    HttpStatus = [int]$response.StatusCode
    HttpHasNewTitle = $httpText.Contains('Panel title="基线对比"')
    HttpHasOldTitle = $httpText.Contains($oldTitle)
} | ConvertTo-Json -Depth 5
