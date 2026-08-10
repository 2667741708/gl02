$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = 'python'
$remote = Join-Path $root 'tools\remote_22012_exec.py'
$remoteScript = Join-Path $root 'tools\remote_guarded_deploy_si_v20_8093_fast.ps1'
$uploads = @(
    "$(Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_8093_ollama_proxy_server.py",
    "$(Join-Path $root '高炉前端数据\智能助手\backend\si_v20_shadow.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_8093_si_v20_shadow.py",
    "$(Join-Path $root '自动诊断服务\abc_rule_config_store.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_8093_abc_rule_config_store.py",
    "$(Join-Path $root '高炉前端数据\si_v20_workbench.html')=C:\Users\Administrator\AppData\Local\Temp\si_v20_8093_si_v20_workbench.html",
    "$(Join-Path $root '高炉前端数据\assets\bf-si-v20-workbench.js')=C:\Users\Administrator\AppData\Local\Temp\si_v20_8093_bf-si-v20-workbench.js",
    "$(Join-Path $root 'tools\run_si_v20_schedule_dispatcher.py')=C:\Users\Administrator\AppData\Local\Temp\si_v20_schedule_dispatcher.py",
    "$(Join-Path $root 'tools\run_22012_si_v20_schedule_dispatcher.ps1')=C:\Users\Administrator\AppData\Local\Temp\run_22012_si_v20_schedule_dispatcher.ps1",
    "$(Join-Path $root 'tools\register_22012_si_v20_schedule_task.ps1')=C:\Users\Administrator\AppData\Local\Temp\register_22012_si_v20_schedule_task.ps1"
)
foreach($path in @($remote,$remoteScript) + ($uploads | ForEach-Object { ($_ -split '=',2)[0] })){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "required local file missing: $path"}
}
& $python $remote --allow-agents-password --no-profile --timeout 40 --workdir 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' --upload-only @($uploads | ForEach-Object { '--upload'; $_ })
if($LASTEXITCODE -ne 0){throw 'remote staging failed; 8093 was not changed'}
& $python $remote --allow-agents-password --no-profile --timeout 180 --workdir 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' --script $remoteScript
if($LASTEXITCODE -ne 0){throw 'remote 8093 deployment failed; inspect the printed backup path and service status'}
