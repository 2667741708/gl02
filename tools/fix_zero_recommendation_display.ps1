$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = (Get-Location).Path
$htmlPath = Get-ChildItem -LiteralPath $root -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "frontend_dashboard_v3.server.html" -File -ErrorAction SilentlyContinue } | Select-Object -First 1 -ExpandProperty FullName
if (-not $htmlPath) { throw "direct frontend html not found" }
$html = [IO.File]::ReadAllText($htmlPath, [Text.Encoding]::UTF8)
if ($html.IndexOf("REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807", [StringComparison]::Ordinal) -ge 0) { Write-Output "already patched"; exit 0 }
$marker = "    const BF_ACTION_STATUS_LABELS ="
$helper = @'
    /* REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807 */
    function bfFiniteControlNumberV3(value) { if (value === null || value === undefined || value === '') return null; const number = Number(value); return Number.isFinite(number) ? number : null }
'@
$pos = $html.IndexOf($marker, [StringComparison]::Ordinal)
if ($pos -lt 0) { throw "action status marker missing" }
$html = $html.Substring(0, $pos) + $helper + $html.Substring($pos)
$oldCardNumbers = "const current = Number(action?.current_value), target = Number(action?.recommended_target), change = Number(action?.recommended_change);"
$newCardNumbers = "const current = bfFiniteControlNumberV3(action?.current_value), target = bfFiniteControlNumberV3(action?.recommended_target), change = bfFiniteControlNumberV3(action?.recommended_change);"
if ($html.IndexOf($oldCardNumbers, [StringComparison]::Ordinal) -ne $pos) { }
if (([regex]::Matches($html, [regex]::Escape($oldCardNumbers))).Count -ne 1) { throw "card numeric declaration not found exactly once" }
$html = $html.Replace($oldCardNumbers, $newCardNumbers)
$oldDetailNumbers = "const unit = action.unit || '', current = Number(action.current_value), target = Number(action.recommended_target), change = Number(action.recommended_change);"
$newDetailNumbers = "const unit = action.unit || '', current = bfFiniteControlNumberV3(action.current_value), target = bfFiniteControlNumberV3(action.recommended_target), change = bfFiniteControlNumberV3(action.recommended_change);"
if (([regex]::Matches($html, [regex]::Escape($oldDetailNumbers))).Count -ne 1) { throw "detail numeric declaration not found exactly once" }
$html = $html.Replace($oldDetailNumbers, $newDetailNumbers)
[IO.File]::WriteAllText($htmlPath, $html, $utf8)
Write-Output $htmlPath
