$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$listener = Get-NetTCPConnection -State Listen -LocalPort 8094 -ErrorAction SilentlyContinue | Select-Object -First 1
$proc = if ($listener) { Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" } else { $null }
$parent = if ($proc -and $proc.ParentProcessId) { Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" } else { $null }
$task = Get-ScheduledTask -TaskName 'V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue
$taskActions = if ($task) { @($task.Actions | Select-Object Execute,Arguments,WorkingDirectory) } else { @() }
$page = try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/?page_probe=20260811' -TimeoutSec 15).Content } catch { '' }
$scriptSrc = [regex]::Matches($page, '<script[^>]+src=["'']([^"'']+)["'']', 'IgnoreCase') | ForEach-Object { $_.Groups[1].Value }
$markers = [regex]::Matches($page, '(?i).{0,80}(?:trend|chart|curve|frontend_dashboard|8094|script).{0,160}') | Select-Object -First 80 | ForEach-Object { $_.Value }
$candidateFiles = @()
foreach ($dir in @((Join-Path $root '高炉前端数据'), (Join-Path $root 'tools'))) {
  if (Test-Path -LiteralPath $dir) {
    $candidateFiles += Get-ChildItem -LiteralPath $dir -File -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.Extension -in @('.html','.ps1','.py','.json') -and $_.Length -lt 2MB } |
      Select-String -Pattern '8094|frontend_dashboard_v3|ollama_proxy_server|V3AutoPreviewProxy8094' -List -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty Path
  }
}
[ordered]@{
  listener = $listener
  process = if ($proc) { $proc | Select-Object ProcessId,ParentProcessId,Name,CommandLine } else { $null }
  parent = if ($parent) { $parent | Select-Object ProcessId,ParentProcessId,Name,CommandLine } else { $null }
  task = if ($task) { $task | Select-Object TaskName,TaskPath,State } else { $null }
  task_actions = $taskActions
  page_length = $page.Length
  script_src = @($scriptSrc)
  page_markers = @($markers)
  candidate_files = @($candidateFiles | Sort-Object -Unique)
} | ConvertTo-Json -Depth 8
