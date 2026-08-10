$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$PageSource = 'C:\Users\Administrator\AppData\Local\Temp\foreman_trend_preview.html'
$CssSource = 'C:\Users\Administrator\AppData\Local\Temp\foreman-trend-preview.css'
$JsSource = 'C:\Users\Administrator\AppData\Local\Temp\foreman-trend-preview.js'
$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'

$pageTarget = Join-Path $ProjectRoot '高炉前端数据\foreman_trend_preview.html'
$cssTarget = Join-Path $ProjectRoot '高炉前端数据\assets\foreman-trend-preview.css'
$jsTarget = Join-Path $ProjectRoot '高炉前端数据\assets\foreman-trend-preview.js'
$backupBase = Join-Path $ProjectRoot 'backups\8093_foreman_trend_preview_20260805'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $backupBase $stamp

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "源文件不存在：$Path"
    }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

Require-File $PageSource
Require-File $CssSource
Require-File $JsSource

$serviceNames = @('BFV4PreviewProxy8093', 'BFV4PreviewWs8768')
$services = @(Get-Service -Name $serviceNames)
if ($services.Count -ne 2 -or ($services | Where-Object Status -ne 'Running')) {
    throw '8093/8768 服务未同时处于 Running，拒绝部署。'
}

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8093,8768 -ErrorAction Stop)
$listenPorts = @($listeners | Select-Object -ExpandProperty LocalPort -Unique)
if (-not ($listenPorts -contains 8093) -or -not ($listenPorts -contains 8768)) {
    throw '8093/8768 监听不完整，拒绝部署。'
}
$pid8093Before = @($listeners | Where-Object LocalPort -eq 8093 | Select-Object -First 1 -ExpandProperty OwningProcess)
$pid8768Before = @($listeners | Where-Object LocalPort -eq 8768 | Select-Object -First 1 -ExpandProperty OwningProcess)

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$targets = @(
    [pscustomobject]@{ Source = $PageSource; Target = $pageTarget; Name = 'foreman_trend_preview.html' },
    [pscustomobject]@{ Source = $CssSource; Target = $cssTarget; Name = 'foreman-trend-preview.css' },
    [pscustomobject]@{ Source = $JsSource; Target = $jsTarget; Name = 'foreman-trend-preview.js' }
)

foreach ($item in $targets) {
    $targetDir = Split-Path -Parent $item.Target
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    if (Test-Path -LiteralPath $item.Target -PathType Leaf) {
        Copy-Item -LiteralPath $item.Target -Destination (Join-Path $backupDir $item.Name) -Force
    }
    $stage = Join-Path $targetDir (".$($item.Name).stage.$stamp")
    Copy-Item -LiteralPath $item.Source -Destination $stage -Force
    Move-Item -LiteralPath $stage -Destination $item.Target -Force
}

$pageUrl = "http://127.0.0.1:8093/foreman_trend_preview.html?ws_port=8768&deploy=$stamp"
$page = Invoke-WebRequest -UseBasicParsing -Uri $pageUrl -TimeoutSec 20
if ($page.StatusCode -ne 200) {
    throw "新页面 HTTP 状态异常：$($page.StatusCode)"
}
if ($page.Content -notmatch 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805') {
    throw '新页面需求标记未从 8093 返回。'
}
$css = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/foreman-trend-preview.css?deploy=$stamp" -TimeoutSec 20
$js = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/foreman-trend-preview.js?deploy=$stamp" -TimeoutSec 20
if ($css.StatusCode -ne 200 -or $js.StatusCode -ne 200) {
    throw '新页面 CSS/JS 资源未同时返回 HTTP 200。'
}

$listenersAfter = @(Get-NetTCPConnection -State Listen -LocalPort 8093,8768 -ErrorAction Stop)
$pid8093After = @($listenersAfter | Where-Object LocalPort -eq 8093 | Select-Object -First 1 -ExpandProperty OwningProcess)
$pid8768After = @($listenersAfter | Where-Object LocalPort -eq 8768 | Select-Object -First 1 -ExpandProperty OwningProcess)
$manifest = [ordered]@{
    requirement = 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805'
    deployed_at = (Get-Date).ToString('o')
    page_url = $pageUrl
    backup_dir = $backupDir
    files = @($targets | ForEach-Object {
        [ordered]@{ name = $_.Name; sha256 = Get-Sha256 $_.Target; target = $_.Target }
    })
    pid_8093_before = $pid8093Before
    pid_8093_after = $pid8093After
    pid_8768_before = $pid8768Before
    pid_8768_after = $pid8768After
    service_8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    service_8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
}
$manifestPath = Join-Path $backupDir 'manifest.json'
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output ($manifest | ConvertTo-Json -Depth 6)
