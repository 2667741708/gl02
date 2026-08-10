$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$engineRoot = Join-Path $root "调控结论生成引擎"
$previewRoot = Join-Path $root "preview_8094_ws8769"
$frontend = Join-Path $root "高炉前端数据"

function Get-ListenerInfo([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return [ordered]@{ port = $Port; pid = $null; commandLine = $null } }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    return [ordered]@{ port = $Port; pid = [int]$listener.OwningProcess; commandLine = if ($process) { $process.CommandLine } else { $null } }
}

function Get-HashOrNull([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
[ordered]@{
    listeners = @(8093,8094,8768,8769 | ForEach-Object { Get-ListenerInfo $_ })
    service8093 = [string](Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction SilentlyContinue).Status
    service8768 = [string](Get-Service -Name "BFV4PreviewWs8768" -ErrorAction SilentlyContinue).Status
    task8094 = [string](Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction SilentlyContinue).State
    engineCoreSha256 = Get-HashOrNull (Join-Path $engineRoot "recommendation\core.py")
    enginePolicySha256 = Get-HashOrNull (Join-Path $engineRoot "policy\three_rules_two_systems.yaml")
    adapterSha256 = Get-HashOrNull (Join-Path $root "自动诊断服务\recommendation_adapter.py")
    bridgeSha256 = Get-HashOrNull (Join-Path $root "自动诊断服务\local_pg_ws_bridge.py")
    previewCoreSha256 = Get-HashOrNull (Join-Path $previewRoot "recommendation_engine\recommendation\core.py")
    previewPolicySha256 = Get-HashOrNull (Join-Path $previewRoot "recommendation_engine\policy\three_rules_two_systems.yaml")
    page8093Sha256 = Get-HashOrNull $page8093
    page8094Sha256 = Get-HashOrNull $page8094
    page8093MultiCondition = if (Test-Path -LiteralPath $page8093) { (Get-Content -LiteralPath $page8093 -Raw -Encoding UTF8).Contains("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805") } else { $false }
    page8094MultiCondition = if (Test-Path -LiteralPath $page8094) { (Get-Content -LiteralPath $page8094 -Raw -Encoding UTF8).Contains("REQ-OPT-MULTI-CONDITION-LLM-REVIEW-20260805") } else { $false }
} | ConvertTo-Json -Depth 6
