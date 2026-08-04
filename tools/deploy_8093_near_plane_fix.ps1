$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
$stageRoot = Join-Path $projectRoot ".codex_stage\8093_near_plane_fix_20260801"
$assetRoot = Join-Path $projectRoot "高炉前端数据\assets"
$required = @(
    "bf3d-surface-camera-guard-8093.js",
    "bf3d-surface-camera-guard-8094.js"
)

foreach ($name in $required) {
    $source = Join-Path $stageRoot $name
    $target = Join-Path $assetRoot $name
    if (-not (Test-Path -LiteralPath $source)) {
        throw "缺少暂存文件：$source"
    }
    if (-not (Test-Path -LiteralPath $target)) {
        throw "缺少8093现有资源：$target"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $projectRoot "backups\8093_near_plane_fix_20260801\$stamp"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

try {
    foreach ($name in $required) {
        Copy-Item -LiteralPath (Join-Path $assetRoot $name) -Destination (Join-Path $backupRoot $name) -Force
        Copy-Item -LiteralPath (Join-Path $stageRoot $name) -Destination (Join-Path $assetRoot $name) -Force
    }

    $entry = Get-Content -LiteralPath (Join-Path $assetRoot "bf3d-surface-camera-guard-8093.js") -Raw
    $shared = Get-Content -LiteralPath (Join-Path $assetRoot "bf3d-surface-camera-guard-8094.js") -Raw
    if ($entry -notmatch "20260801-8093-near-plane-r4") {
        throw "8093入口未更新缓存版本"
    }
    if ($shared -notmatch 'PORT_SCOPE === "8093" \? 0\.05 : null') {
        throw "共享守卫缺少8093专属0.05m近裁剪面锁定"
    }
    if ($shared -notmatch 'enforceSafeNearPlane\("periodic-guard"\)') {
        throw "共享守卫缺少周期近裁剪面纠偏"
    }
} catch {
    foreach ($name in $required) {
        $backup = Join-Path $backupRoot $name
        if (Test-Path -LiteralPath $backup) {
            Copy-Item -LiteralPath $backup -Destination (Join-Path $assetRoot $name) -Force
        }
    }
    throw
}

$files = foreach ($name in $required) {
    $target = Join-Path $assetRoot $name
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $target
    [ordered]@{
        name = $name
        path = $target
        sha256 = $hash.Hash
        length = (Get-Item -LiteralPath $target).Length
    }
}

[ordered]@{
    deployed = $true
    scope = "8093-only-near-plane-lock"
    safe_near_plane_m = 0.05
    backup = $backupRoot
    files = $files
} | ConvertTo-Json -Depth 5
