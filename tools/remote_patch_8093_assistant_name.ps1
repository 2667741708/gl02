$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$projectRoot = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontendDirectory = Join-Path $projectRoot "高炉前端数据"
$pagePath = Join-Path $frontendDirectory "frontend_dashboard_v3.server.html"
$preview8094Path = Join-Path $frontendDirectory "frontend_dashboard_v3.8094_preview.server.html"
$oldText = "['qa', '智能问答/知识助手', '☻']"
$newText = "['qa', '智能助手', '☻']"

if (-not (Test-Path -LiteralPath $pagePath)) {
    throw "8093 page not found: $pagePath"
}

$preview8094HashBefore = if (Test-Path -LiteralPath $preview8094Path) {
    (Get-FileHash -LiteralPath $preview8094Path -Algorithm SHA256).Hash
} else {
    $null
}

$content = [IO.File]::ReadAllText($pagePath, [Text.Encoding]::UTF8)
$oldCount = ([regex]::Matches($content, [regex]::Escape($oldText))).Count
$newCount = ([regex]::Matches($content, [regex]::Escape($newText))).Count
$changed = $false
$backupDirectory = $null

if ($oldCount -eq 1 -and $newCount -eq 0) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDirectory = Join-Path $projectRoot "backups\8093_assistant_name_20260804\$stamp"
    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    $backupPath = Join-Path $backupDirectory (Split-Path -Leaf $pagePath)
    $atomicBackupPath = Join-Path $backupDirectory "frontend_dashboard_v3.server.atomic-original.html"
    Copy-Item -LiteralPath $pagePath -Destination $backupPath -Force

    $updated = $content.Replace($oldText, $newText)
    $temporaryPath = "$pagePath.assistant-name-$stamp.tmp"
    [IO.File]::WriteAllText($temporaryPath, $updated, [Text.UTF8Encoding]::new($false))
    try {
        [IO.File]::Replace($temporaryPath, $pagePath, $atomicBackupPath, $true)
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
    $changed = $true
} elseif (-not ($oldCount -eq 0 -and $newCount -eq 1)) {
    throw "Unexpected 8093 navigation title counts: old=$oldCount new=$newCount"
}

$finalContent = [IO.File]::ReadAllText($pagePath, [Text.Encoding]::UTF8)
$finalOldCount = ([regex]::Matches($finalContent, [regex]::Escape($oldText))).Count
$finalNewCount = ([regex]::Matches($finalContent, [regex]::Escape($newText))).Count
if ($finalOldCount -ne 0 -or $finalNewCount -ne 1) {
    throw "8093 navigation title verification failed: old=$finalOldCount new=$finalNewCount"
}

$preview8094HashAfter = if (Test-Path -LiteralPath $preview8094Path) {
    (Get-FileHash -LiteralPath $preview8094Path -Algorithm SHA256).Hash
} else {
    $null
}
if ($preview8094HashBefore -ne $preview8094HashAfter) {
    throw "8094 preview page changed unexpectedly"
}

$cacheBust = [Uri]::EscapeDataString((Get-Date).ToString("yyyyMMddHHmmssfff"))
$http = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=$cacheBust" -TimeoutSec 10
$httpOldCount = ([regex]::Matches($http.Content, [regex]::Escape($oldText))).Count
$httpNewCount = ([regex]::Matches($http.Content, [regex]::Escape($newText))).Count
if ([int]$http.StatusCode -ne 200 -or $httpOldCount -ne 0 -or $httpNewCount -ne 1) {
    throw "8093 HTTP verification failed: status=$($http.StatusCode) old=$httpOldCount new=$httpNewCount"
}

[pscustomobject]@{
    schema = "ops.8093.assistant-name.v1"
    changed = $changed
    backup_directory = $backupDirectory
    page_sha256 = (Get-FileHash -LiteralPath $pagePath -Algorithm SHA256).Hash
    http_status = [int]$http.StatusCode
    http_old_count = $httpOldCount
    http_new_count = $httpNewCount
    preview_8094_sha256_before = $preview8094HashBefore
    preview_8094_sha256_after = $preview8094HashAfter
    preview_8094_unchanged = $preview8094HashBefore -eq $preview8094HashAfter
} | ConvertTo-Json -Depth 4
