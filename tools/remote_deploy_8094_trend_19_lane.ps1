$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$target = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$stage = "C:\Users\Administrator\AppData\Local\Temp\frontend_dashboard_v3.8094_preview.trend19.html"
$expectedBeforeHash = "C93F33A3BA3971A4CF86DCC92350A88AC0AADEB52CC59F79DDE3E7C01D3CA89F"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

foreach ($path in @($target, $stage)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required file is missing: $path" }
}
$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
if ($beforeHash -ne $expectedBeforeHash) {
    throw "8094 changed after preflight. Expected $expectedBeforeHash, got $beforeHash"
}
$stageText = Get-Content -LiteralPath $stage -Raw -Encoding UTF8
foreach ($marker in @(
    "REQ-TREND-19-LANE-MERGE-20260807",
    "19个核心变量趋势与预测",
    "const TREND_PREDICT_IDS=['P_top','P_top_gas_A','P_top_gas_B','P_top_gas_C','P_top_gas_D','T_top','T_top_A','T_top_B','T_top_C','T_top_D','Q_blast','P_blast_cold','P_blast','T_blast','PI','DP_total','DP_upper','DP_lower','GasUtil']",
    "target_ids: TREND_PREDICT_IDS",
    "TREND_PREDICT_IDS.includes(id)",
    "OPS-8094-MULTI-CONDITION-REVIEW-20260805",
    "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"
)) {
    if (-not $stageText.Contains($marker)) { throw "Staged payload marker is missing: $marker" }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
if ($task.State -ne "Running") { throw "8094 managed task is not running" }
$beforePids = [ordered]@{}
foreach ($port in 8093,8094,8768,8770,11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $beforePids[[string]$port] = [int]$listener.OwningProcess
}
$html8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$hash8093Before = (Get-FileHash -Algorithm SHA256 -LiteralPath $html8093).Hash
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8094_trend_19_lane_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$backupFile = Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html"
Copy-Item -LiteralPath $target -Destination $backupFile -Force
$tempTarget = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html.trend19.tmp"
$replaceBackup = Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html.replace.bak"

try {
    Copy-Item -LiteralPath $stage -Destination $tempTarget -Force
    [IO.File]::Replace($tempTarget, $target, $replaceBackup, $true)
    $cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri "http://127.0.0.1:8094/?trend19=$cacheBust#trend"
    if ($response.StatusCode -ne 200) { throw "8094 returned HTTP $($response.StatusCode)" }
    foreach ($marker in @("REQ-TREND-19-LANE-MERGE-20260807", "19个核心变量趋势与预测")) {
        if (-not $response.Content.Contains($marker)) { throw "8094 HTTP is missing marker: $marker" }
    }
    $afterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
    $stageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stage).Hash
    if ($afterHash -ne $stageHash) { throw "Installed 8094 hash differs from staged payload" }
    $afterPids = [ordered]@{}
    foreach ($port in 8093,8094,8768,8770,11434) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
        $afterPids[[string]$port] = [int]$listener.OwningProcess
        if ($afterPids[[string]$port] -ne $beforePids[[string]$port]) {
            throw "Protected listener PID changed on port $port"
        }
    }
    $hash8093After = (Get-FileHash -Algorithm SHA256 -LiteralPath $html8093).Hash
    if ($hash8093After -ne $hash8093Before) { throw "8093 HTML changed during 8094-only deployment" }
    if ((Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State -ne "Running") {
        throw "8094 managed task stopped after hot deployment"
    }
    [ordered]@{
        ok = $true
        requirement = "REQ-TREND-19-LANE-MERGE-20260807"
        deployed_at = (Get-Date).ToString("s")
        backup = $backup
        before_hash = $beforeHash
        after_hash = $afterHash
        http_status = [int]$response.StatusCode
        restart_performed = $false
        task8094 = "Running"
        pids_before = $beforePids
        pids_after = $afterPids
        html8093_unchanged = $true
    } | ConvertTo-Json -Depth 5
}
catch {
    if (Test-Path -LiteralPath $backupFile) {
        Copy-Item -LiteralPath $backupFile -Destination $target -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $tempTarget) {
        Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue
    }
    throw
}
