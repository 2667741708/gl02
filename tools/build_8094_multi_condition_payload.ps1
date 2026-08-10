$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$packageRoot = Join-Path $repo "logs\deployment\8094_multi_condition_20260805\package_r8"
$stage = Join-Path $packageRoot "staging"
$archive = Join-Path $packageRoot "bf8094multi.zip"
if (Test-Path -LiteralPath $stage) { throw "Payload staging path already exists: $stage" }
if (Test-Path -LiteralPath $archive) { throw "Payload archive already exists: $archive" }

New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage "preview_8094_ws8769\recommendation_engine") -Force | Out-Null

$files = [ordered]@{
    "高炉前端数据\frontend_dashboard_v3.server.html" = "frontend_source.html"
    "tools\patch_8094_multi_condition_review.py" = "patch_8094_multi_condition_review.py"
    "tools\verify_8094_multi_condition_package.py" = "verify_8094_multi_condition_package.py"
    "tools\verify_8094_multi_condition_runtime.py" = "verify_8094_multi_condition_runtime.py"
    "高炉前端数据\智能助手\backend\ollama_proxy_server.py" = "ollama_proxy_server_8094.py"
    "高炉前端数据\智能助手\backend\diagnosis_model_review.py" = "diagnosis_model_review_8094.py"
    "tools\restart_22012_8094_preview.ps1" = "restart_22012_8094_preview.ps1"
    "tools\run_22012_8094_preview.ps1" = "run_22012_8094_preview.ps1"
    "tools\run_22012_8094_ws8769.ps1" = "run_22012_8094_ws8769.ps1"
    "tools\run_22012_8094_ws8769.py" = "run_22012_8094_ws8769.py"
    "自动诊断服务\local_pg_ws_bridge.py" = "preview_8094_ws8769\local_pg_ws_bridge.py"
    "自动诊断服务\recommendation_adapter.py" = "preview_8094_ws8769\recommendation_adapter.py"
}
foreach ($entry in $files.GetEnumerator()) {
    $source = Join-Path $repo $entry.Key
    $destination = Join-Path $stage $entry.Value
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Payload source missing: $source" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

$isolatedProxyPath = Join-Path $stage "ollama_proxy_server_8094.py"
$isolatedProxyText = Get-Content -LiteralPath $isolatedProxyPath -Raw -Encoding UTF8
$isolatedProxyText = $isolatedProxyText.Replace(
    "import diagnosis_model_review",
    "import diagnosis_model_review_8094 as diagnosis_model_review"
)
[IO.File]::WriteAllText($isolatedProxyPath, $isolatedProxyText, [Text.UTF8Encoding]::new($false))

Copy-Item -LiteralPath (Join-Path $repo "调控结论生成引擎\recommendation") `
    -Destination (Join-Path $stage "preview_8094_ws8769\recommendation_engine\recommendation") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repo "调控结论生成引擎\policy") `
    -Destination (Join-Path $stage "preview_8094_ws8769\recommendation_engine\policy") -Recurse -Force

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal
[ordered]@{
    ok = $true
    archive = $archive
    sha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    length = (Get-Item -LiteralPath $archive).Length
    fileCount = @(Get-ChildItem -LiteralPath $stage -Recurse -File).Count
} | ConvertTo-Json -Depth 4
