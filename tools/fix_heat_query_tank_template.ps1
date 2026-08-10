$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$path = @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'bf-heat-performance-quality-8093-query-v2.js' | Where-Object { $_.FullName -notmatch '\\logs\\|\\tmp\\|\\backups\\' } | Select-Object -ExpandProperty FullName)
if ($path.Count -ne 1) { throw "expected one query asset, found $($path.Count)" }
$text = [IO.File]::ReadAllText($path[0])
$prefix = '\u5DF2\u6D3E\u7F50\u53F7'
$start = $text.IndexOf($prefix)
$end = $text.IndexOf('</div>', $start)
if ($start -lt 0 -or $end -lt 0) { throw 'tank template anchor not found' }
$replacement = '\u5DF2\u6D3E\u7F50\u53F7\uFF1A${esc(tankList(item))}'
$text = $text.Substring(0, $start) + $replacement + $text.Substring($end)
[IO.File]::WriteAllText($path[0], $text, [Text.UTF8Encoding]::new($false))
Write-Output 'tank-template-fixed'
