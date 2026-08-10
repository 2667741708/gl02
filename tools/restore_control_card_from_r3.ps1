$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = (Get-Location).Path
$sourcePath = Get-ChildItem -LiteralPath $root -Recurse -Filter "frontend_dashboard_v3.server.html" -File | Where-Object { $_.FullName -match "recommendation_sync_20260806_r3" } | Select-Object -First 1 -ExpandProperty FullName
$targetPath = Get-ChildItem -LiteralPath $root -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "frontend_dashboard_v3.server.html" -File -ErrorAction SilentlyContinue } | Select-Object -First 1 -ExpandProperty FullName
if (-not $sourcePath -or -not $targetPath) { throw "source or target frontend file missing" }
$source = [IO.File]::ReadAllText($sourcePath, [Text.Encoding]::UTF8)
$target = [IO.File]::ReadAllText($targetPath, [Text.Encoding]::UTF8)
$sourceStart = $source.IndexOf("    function BFControlAdviceCardV2", [StringComparison]::Ordinal)
$sourceEnd = $source.IndexOf("    function BFRecommendationSummaryV2", $sourceStart, [StringComparison]::Ordinal)
$targetStart = $target.IndexOf("    function BFControlAdviceCardV2", [StringComparison]::Ordinal)
$targetEnd = $target.IndexOf("    function BFRecommendationSummaryV2", $targetStart, [StringComparison]::Ordinal)
if ($sourceStart -lt 0 -or $sourceEnd -lt 0 -or $targetStart -lt 0 -or $targetEnd -lt 0) { throw "card boundaries missing" }
$original = $source.Substring($sourceStart, $sourceEnd - $sourceStart)
$target = $target.Substring(0, $targetStart) + $original + $target.Substring($targetEnd)
[IO.File]::WriteAllText($targetPath, $target, $utf8)
Write-Output $targetPath
