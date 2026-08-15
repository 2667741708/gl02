$ErrorActionPreference = 'Stop'
$out = [ordered]@{}
foreach ($port in @(8095,8096)) {
  $page = try { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/?curve_probe=20260811" -TimeoutSec 15).Content } catch { '' }
  $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
  $proc = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" } else { $null }
  $parent = if ($proc) { Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" } else { $null }
  $src = [regex]::Matches($page, '<script[^>]+src=["'']([^"'']+)["'']', 'IgnoreCase') | ForEach-Object { $_.Groups[1].Value }
  $lines = [regex]::Matches($page, '(?i).{0,80}(?:ChartBox|echarts|trend-toolbar|dataZoom|curve|sensor).{0,180}') | Select-Object -First 30 | ForEach-Object { $_.Value }
  $out[[string]$port] = [ordered]@{ bytes = $page.Length; scripts = @($src); markers = @($lines); process = if ($proc) { $proc | Select-Object ProcessId,ParentProcessId,Name,CommandLine } else { $null }; parent = if ($parent) { $parent | Select-Object ProcessId,ParentProcessId,Name,CommandLine } else { $null } }
}
$out | ConvertTo-Json -Depth 8
