$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$backend = Join-Path $root '高炉前端数据\智能助手\backend'
$frontend = Join-Path $root '高炉前端数据'
$taskPath = '\BlastFurnaceServices\'
$taskNames = @(
    'SiV20StrictHourlyPrediction',
    'SiV20ScheduledShadowPrediction',
    'V3AutoPreviewProxy8094'
)

$files = @(
    'ollama_proxy_server.py',
    'ollama_proxy_server_8094.py',
    'si_v20_shadow.py',
    'si_v20_strict_context.py',
    'heat_performance_quality.py',
    'models\si_v20_strict_context_lgbm_v1.json.gz'
)
$fileState = @()
foreach ($relative in $files) {
    $path = Join-Path $backend $relative
    $fileState += [ordered]@{
        relative = $relative
        exists = Test-Path -LiteralPath $path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $path -PathType Leaf) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
    }
}
$taskState = @()
foreach ($name in $taskNames) {
    $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $name -ErrorAction SilentlyContinue
    $taskState += [ordered]@{
        name = $name
        exists = $null -ne $task
        state = if ($task) { $task.State.ToString() } else { $null }
        actions = if ($task) { @($task.Actions | ForEach-Object { [ordered]@{ execute=$_.Execute; arguments=$_.Arguments; working_directory=$_.WorkingDirectory } }) } else { @() }
    }
}
$ports = @()
foreach ($port in @(8093, 8094, 8768, 8770, 11434)) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $process = if ($listener) { Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$listener.OwningProcess) -ErrorAction SilentlyContinue } else { $null }
    $ports += [ordered]@{
        port=$port
        listening=[bool]$listener
        pid=if($listener){[int]$listener.OwningProcess}else{$null}
        command_line=if($process){$process.CommandLine}else{$null}
    }
}
$isolatedPath = Join-Path $backend 'ollama_proxy_server_8094.py'
$isolatedText = if (Test-Path -LiteralPath $isolatedPath -PathType Leaf) { Get-Content -LiteralPath $isolatedPath -Raw -Encoding UTF8 } else { '' }

[ordered]@{
    schema = 'ops.si-v20.strict-hourly-surfaces-probe.v1'
    root = $root
    files = $fileState
    tasks = $taskState
    ports = $ports
    page = Test-Path -LiteralPath (Join-Path $frontend 'si_v20_workbench.html') -PathType Leaf
    isolated_8094_imports_common = $isolatedText.Contains('from ollama_proxy_server import') -or $isolatedText.Contains('import ollama_proxy_server')
    runner_8094_sha256 = (Get-FileHash -LiteralPath (Join-Path $root 'tools\run_22012_8094_preview.ps1') -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 8
