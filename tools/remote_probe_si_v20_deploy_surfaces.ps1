$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$frontend = Join-Path $root '高炉前端数据'
$backend = Join-Path $frontend '智能助手\backend'
$paths = @(
    (Join-Path $frontend 'frontend_dashboard_v3.server.html'),
    (Join-Path $frontend 'frontend_dashboard_v3.8094_preview.server.html'),
    (Join-Path $backend 'ollama_proxy_server.py'),
    (Join-Path $backend 'ollama_proxy_server_8094.py'),
    (Join-Path $frontend 'si_v20_workbench.html'),
    (Join-Path $frontend 'assets\bf-si-v20-workbench.js'),
    (Join-Path $root 'tools\run_si_v20_schedule_dispatcher.py'),
    (Join-Path $root 'tools\run_22012_si_v20_schedule_dispatcher.ps1'),
    (Join-Path $root 'tools\register_22012_si_v20_schedule_task.ps1'),
    (Join-Path $backend 'heat_performance_quality.py'),
    (Join-Path $root 'tools\restart_22012_8094_preview.ps1'),
    (Join-Path $root 'tools\manage_22012_managed_services.ps1'),
    (Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json')
)
$files = foreach ($path in $paths) {
    [ordered]@{
        path = $path
        exists = Test-Path -LiteralPath $path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $path -PathType Leaf) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
    }
}
$listeners = foreach ($port in @(8093, 8094, 8768, 8770, 11434)) {
    $item = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    [ordered]@{ port = $port; pid = if ($item) { [int]$item.OwningProcess } else { $null } }
}
$task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue
$scheduleTask = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction' -ErrorAction SilentlyContinue
$processes = foreach ($listener in $listeners) {
    if ($listener.pid) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.pid)" -ErrorAction SilentlyContinue
        [ordered]@{ port = $listener.port; pid = $listener.pid; command_line = if ($process) { $process.CommandLine } else { $null } }
    }
}
[ordered]@{
    checked_at = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    files = $files
    listeners = $listeners
    processes = $processes
    task8094 = if ($task) { [string]$task.State } else { $null }
    schedule_task = if ($scheduleTask) { [string]$scheduleTask.State } else { $null }
    python311 = Test-Path -LiteralPath 'C:\Program Files\Python311\python.exe' -PathType Leaf
} | ConvertTo-Json -Depth 5
