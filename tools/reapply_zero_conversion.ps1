$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = (Get-Location).Path
$htmlPath = Get-ChildItem -LiteralPath $root -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "frontend_dashboard_v3.server.html" -File -ErrorAction SilentlyContinue } | Select-Object -First 1 -ExpandProperty FullName
$html = [IO.File]::ReadAllText($htmlPath, [Text.Encoding]::UTF8)
$oldCard = "const current = Number(action?.current_value), target = Number(action?.recommended_target), change = Number(action?.recommended_change);"
$newCard = "const current = bfFiniteControlNumberV3(action?.current_value), target = bfFiniteControlNumberV3(action?.recommended_target), change = bfFiniteControlNumberV3(action?.recommended_change);"
if ($html.IndexOf($oldCard, [StringComparison]::Ordinal) -ge 0) { $html = $html.Replace($oldCard, $newCard) }
$oldDetail = "const unit = action.unit || '', current = Number(action.current_value), target = Number(action.recommended_target), change = Number(action.recommended_change);"
$newDetail = "const unit = action.unit || '', current = bfFiniteControlNumberV3(action.current_value), target = bfFiniteControlNumberV3(action.recommended_target), change = bfFiniteControlNumberV3(action.recommended_change);"
if ($html.IndexOf($oldDetail, [StringComparison]::Ordinal) -ge 0) { $html = $html.Replace($oldDetail, $newDetail) }
[IO.File]::WriteAllText($htmlPath, $html, $utf8)
Write-Output $htmlPath
