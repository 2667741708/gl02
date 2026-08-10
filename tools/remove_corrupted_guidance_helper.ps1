$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = (Get-Location).Path
$targetPath = Get-ChildItem -LiteralPath $root -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "frontend_dashboard_v3.server.html" -File -ErrorAction SilentlyContinue } | Select-Object -First 1 -ExpandProperty FullName
$target = [IO.File]::ReadAllText($targetPath, [Text.Encoding]::UTF8)
$helperStart = $target.IndexOf("    function bfGuidanceRpcV3", [StringComparison]::Ordinal)
$helperEnd = $target.IndexOf("    function BFControlAdviceCardV2", $helperStart, [StringComparison]::Ordinal)
if ($helperStart -ge 0 -and $helperEnd -gt $helperStart) { $target = $target.Substring(0, $helperStart) + $target.Substring($helperEnd) }
[IO.File]::WriteAllText($targetPath, $target, $utf8)
Write-Output $targetPath
