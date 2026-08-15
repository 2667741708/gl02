$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$paths = @(
  (Join-Path $root '高炉前端数据\foreman_trend_preview.html'),
  (Join-Path $root '高炉前端数据\assets\foreman-trend-preview.js'),
  (Join-Path $root '高炉前端数据\assets\curve-inspector.js')
)
$rows = foreach ($path in $paths) { [ordered]@{ path = $path; exists = Test-Path -LiteralPath $path; hash = if (Test-Path -LiteralPath $path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }; marker = if (Test-Path -LiteralPath $path) { (Get-Content -LiteralPath $path -Raw -Encoding UTF8).Contains('curve-inspector') } else { $false } } }
$backup = Get-ChildItem -LiteralPath (Join-Path $root 'backups') -Directory -ErrorAction SilentlyContinue | Where-Object Name -like 'curve_inspector_8093*' | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | Select-Object FullName,LastWriteTime
$stage = Get-ChildItem -LiteralPath 'C:\Users\Administrator\AppData\Local\Temp\curve_inspector_8093' -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*curve_inspector*' -or $_.CommandLine -like '*manage_22012_managed_services*' } | Select-Object ProcessId,ParentProcessId,Name,CommandLine
$mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment'); $mutexResult = $mutex.WaitOne(0); if ($mutexResult) { $mutex.ReleaseMutex() }; $mutex.Dispose()
$tasks = @('V3AutoPreviewProxy8094','V3AutoPreviewWs8768','BFV4PreviewProxy8093','BFV4PreviewWs8768') | ForEach-Object { $t = Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue; [ordered]@{ name = $_; state = if ($t) { $t.State.ToString() } else { $null } } }
$p8094 = Get-NetTCPConnection -State Listen -LocalPort 8094 -ErrorAction SilentlyContinue | Select-Object -First 1
$p8094Proc = if ($p8094) { Get-CimInstance Win32_Process -Filter "ProcessId=$($p8094.OwningProcess)" | Select-Object ProcessId,ParentProcessId,Name,CommandLine } else { $null }
$taskInfo8094 = Get-ScheduledTaskInfo -TaskName 'V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue | Select-Object LastRunTime,LastTaskResult,NextRunTime
$page8094 = try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/?curve_inspector_probe=1' -TimeoutSec 10).Content } catch { '' }
[ordered]@{ service = (Get-Service BFV4PreviewProxy8093).Status.ToString(); p8093 = @(Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue | Select-Object -First 1 OwningProcess); p8094 = @($p8094); p8094_process = $p8094Proc; p8094_task_info = $taskInfo8094; p8094_has_helper = $page8094.Contains('curve-inspector.js'); p8094_has_range = $page8094.Contains('bf-curve-range-controls'); p8768 = @(Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction SilentlyContinue | Select-Object -First 1 OwningProcess); p8770 = @(Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction SilentlyContinue | Select-Object -First 1 OwningProcess); files = $rows; backup = $backup; stage = $stage; processes = $procs; tasks = $tasks; mutex_available = $mutexResult } | ConvertTo-Json -Depth 6
