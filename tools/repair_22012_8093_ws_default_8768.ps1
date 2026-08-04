$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null

$htmlPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html"
if (-not (Test-Path -LiteralPath $htmlPath)) {
    throw "8093 preview HTML not found: $htmlPath"
}

$text = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8
$old = "new URLSearchParams(window.location.search).get('ws_port')||'8767'"
$new = "new URLSearchParams(window.location.search).get('ws_port')||'8768'"
if ($text.Contains($old)) {
    $backup = "$htmlPath.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item -LiteralPath $htmlPath -Destination $backup -Force
    $text = $text.Replace($old, $new)
    Set-Content -LiteralPath $htmlPath -Value $text -Encoding UTF8
    Write-Host "patched=true"
    Write-Host "backup=$backup"
} elseif ($text.Contains($new)) {
    Write-Host "patched=false"
    Write-Host "reason=already_8768"
} else {
    throw "Cannot find WS_PORT default expression in $htmlPath"
}

$verify = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8
[pscustomobject]@{
    Path = $htmlPath
    HasDefault8768 = $verify.Contains($new)
    HasDefault8767 = $verify.Contains($old)
    HasDiagnosisHistory = $verify.Contains("diagnosis_history")
    HasForemanCoreIds = $verify.Contains("FOREMAN_CORE_IDS")
    HasO2Rate = $verify.Contains("O2_rate")
    HasStatic20m35 = $verify.Contains("P_static_20m35")
    Length = $verify.Length
    LastWriteTime = (Get-Item -LiteralPath $htmlPath).LastWriteTime
} | ConvertTo-Json -Depth 4
