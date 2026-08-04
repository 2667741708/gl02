$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$page = Get-ChildItem -LiteralPath $root -Filter 'frontend_dashboard_v3.server.html' -Recurse |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'assets') } |
    Select-Object -First 1
if (-not $page) { throw '8093 frontend page not found' }
$css = Join-Path $page.DirectoryName 'assets\bf3d-furnace-summary-readability-8093.css'
$pageText = Get-Content -LiteralPath $page.FullName -Raw -Encoding UTF8
$cssText = Get-Content -LiteralPath $css -Raw -Encoding UTF8
$result = [ordered]@{
    schema = 'verify.8093.furnace-summary-readability.v1'
    service8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    service8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    listen8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue)
    listen8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)
    pageLinked = $pageText.Contains('bf3d-furnace-summary-readability-8093.css?v=20260802-expanded7-r2')
    cssScoped = $cssText.Contains('.layered-cad-stage .furnace-layer-callouts.follow-model .furnace-layer-card')
    compactWidth198 = $cssText.Contains('width: 198px !important')
    ellipsisRemoved = $cssText.Contains('text-overflow: clip !important')
    unitsPreserved = $cssText.Contains('display: inline !important')
    pointBillboardsUntouched = -not $cssText.Contains('.furnace-billboard')
    pageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $page.FullName).Hash
    cssHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $css).Hash
    backups = @(
        Get-ChildItem -LiteralPath (Join-Path $root 'backups\8093_furnace_summary_readability_20260802') -Directory |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 2 -ExpandProperty FullName
    )
}
$result | ConvertTo-Json -Depth 4
