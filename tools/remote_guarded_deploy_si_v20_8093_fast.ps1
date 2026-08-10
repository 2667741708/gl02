$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$frontend = Join-Path $root '高炉前端数据'
$backend = Join-Path $frontend '智能助手\backend'
$assets = Join-Path $frontend 'assets'
$server = Join-Path $backend 'ollama_proxy_server.py'
$module = Join-Path $backend 'si_v20_shadow.py'
$abcStore = Join-Path $root '自动诊断服务\abc_rule_config_store.py'
$page = Join-Path $frontend 'si_v20_workbench.html'
$asset = Join-Path $assets 'bf-si-v20-workbench.js'
$dispatcher = Join-Path $root 'tools\run_si_v20_schedule_dispatcher.py'
$dispatcherRunner = Join-Path $root 'tools\run_22012_si_v20_schedule_dispatcher.ps1'
$taskRegistrar = Join-Path $root 'tools\register_22012_si_v20_schedule_task.ps1'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$guardConfig = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$tempRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$uploadedServer = Join-Path $tempRoot 'si_v20_8093_ollama_proxy_server.py'
$uploadedModule = Join-Path $tempRoot 'si_v20_8093_si_v20_shadow.py'
$uploadedAbc = Join-Path $tempRoot 'si_v20_8093_abc_rule_config_store.py'
$uploadedPage = Join-Path $tempRoot 'si_v20_8093_si_v20_workbench.html'
$uploadedAsset = Join-Path $tempRoot 'si_v20_8093_bf-si-v20-workbench.js'
$uploadedDispatcher = Join-Path $tempRoot 'si_v20_schedule_dispatcher.py'
$uploadedDispatcherRunner = Join-Path $tempRoot 'run_22012_si_v20_schedule_dispatcher.ps1'
$uploadedTaskRegistrar = Join-Path $tempRoot 'register_22012_si_v20_schedule_task.ps1'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\si_v20_workbench_8093_20260808\$stamp"

function Wait-ServiceState { param([string]$Name,[string]$State,[int]$TimeoutSeconds=120)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do { if((Get-Service -Name $Name).Status.ToString() -eq $State){return}; Start-Sleep -Milliseconds 300 } while([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $State"
}
function Wait-Port { param([int]$Port,[bool]$Listening,[int]$TimeoutSeconds=120)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do { $found=[bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1); if($found -eq $Listening){return}; Start-Sleep -Milliseconds 500 } while([DateTime]::UtcNow -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}
function Atomic-Install { param([string]$Source,[string]$Target)
    $tmp = "$Target.si_v20_installing"
    Copy-Item -LiteralPath $Source -Destination $tmp -Force
    Move-Item -LiteralPath $tmp -Destination $Target -Force
}
function Save-File { param([string]$Source,[string]$Name)
    if(Test-Path -LiteralPath $Source -PathType Leaf){ Copy-Item -LiteralPath $Source -Destination (Join-Path $backup $Name) -Force; return $true }
    return $false
}
function Restore-File { param([string]$Name,[string]$Target,[bool]$Existed)
    $source = Join-Path $backup $Name
    if($Existed -and (Test-Path -LiteralPath $source -PathType Leaf)){ Atomic-Install $source $Target }
    elseif(-not $Existed -and (Test-Path -LiteralPath $Target -PathType Leaf)){ Remove-Item -LiteralPath $Target -Force }
}
function Get-HttpJson { param([string]$Uri,[int]$Attempts=12)
    $last=$null
    for($i=0;$i -lt $Attempts;$i++){
        try { return Invoke-RestMethod -UseBasicParsing -Uri $Uri -TimeoutSec 15 }
        catch { $last=$_; Start-Sleep -Seconds 2 }
    }
    throw $last
}

foreach($path in @($manager,$guardConfig,$uploadedServer,$uploadedModule,$uploadedAbc,$uploadedPage,$uploadedAsset,$uploadedDispatcher,$uploadedDispatcherRunner,$uploadedTaskRegistrar)){
    if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "required file missing: $path"}
}
& 'C:\Program Files\Python311\python.exe' -X utf8 -m py_compile $uploadedServer $uploadedModule $uploadedAbc $uploadedDispatcher
if($LASTEXITCODE -ne 0){throw 'V20 8093 staged Python syntax check failed'}
if((Get-Service -Name BFV4PreviewProxy8093).Status.ToString() -ne 'Running'){throw '8093 guard must be running before deployment'}
$listener8768Before = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if(-not $listener8768Before){throw '8768 must be listening before deployment'}
$protectedBefore = @{}
foreach($port in @(8094,8770,11434)){
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if(-not $listener){throw "protected port $port must be listening before deployment"}
    $protectedBefore[[string]$port] = [int]$listener.OwningProcess
}
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$serverExisted=Save-File $server 'ollama_proxy_server.py'
$moduleExisted=Save-File $module 'si_v20_shadow.py'
$abcExisted=Save-File $abcStore 'abc_rule_config_store.py'
$pageExisted=Save-File $page 'si_v20_workbench.html'
$assetExisted=Save-File $asset 'bf-si-v20-workbench.js'
$dispatcherExisted=Save-File $dispatcher 'run_si_v20_schedule_dispatcher.py'
$dispatcherRunnerExisted=Save-File $dispatcherRunner 'run_22012_si_v20_schedule_dispatcher.ps1'
$taskRegistrarExisted=Save-File $taskRegistrar 'register_22012_si_v20_schedule_task.ps1'
$installed=$false
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState 'BFV4PreviewProxy8093' 'Stopped'
    Wait-Port 8093 $false
    Atomic-Install $uploadedServer $server
    Atomic-Install $uploadedModule $module
    Atomic-Install $uploadedAbc $abcStore
    Atomic-Install $uploadedPage $page
    Atomic-Install $uploadedAsset $asset
    Atomic-Install $uploadedDispatcher $dispatcher
    Atomic-Install $uploadedDispatcherRunner $dispatcherRunner
    Atomic-Install $uploadedTaskRegistrar $taskRegistrar
    $installed=$true
}
catch {
    Restore-File 'ollama_proxy_server.py' $server $serverExisted
    Restore-File 'si_v20_shadow.py' $module $moduleExisted
    Restore-File 'abc_rule_config_store.py' $abcStore $abcExisted
    Restore-File 'si_v20_workbench.html' $page $pageExisted
    Restore-File 'bf-si-v20-workbench.js' $asset $assetExisted
    Restore-File 'run_si_v20_schedule_dispatcher.py' $dispatcher $dispatcherExisted
    Restore-File 'run_22012_si_v20_schedule_dispatcher.ps1' $dispatcherRunner $dispatcherRunnerExisted
    Restore-File 'register_22012_si_v20_schedule_task.ps1' $taskRegistrar $taskRegistrarExisted
    throw
}
finally {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig | Out-Null
        Wait-ServiceState 'BFV4PreviewProxy8093' 'Running'
        Wait-Port 8093 $true
    }
    catch { Write-Error ("8093 guard restoration failed: " + $_.Exception.Message); throw }
}

if(-not $installed){throw 'V20 files were not installed'}
$status = Get-HttpJson 'http://127.0.0.1:8093/api/si-v20/status?limit=12'
if(-not $status.ok){throw 'V20 status API returned ok=false'}
if(-not ($status.PSObject.Properties.Name -contains 'candidate_targets')){throw 'candidate_targets missing from status API'}
if($status.require_login -ne $false){throw 'V20 workbench unexpectedly requires login'}
$pageResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/si_v20_workbench.html?cb=20260808' -TimeoutSec 30
if($pageResponse.StatusCode -ne 200){throw "standalone page HTTP $($pageResponse.StatusCode)"}
if(-not $pageResponse.Content.Contains('bf-si-v20-workbench.js')){throw 'standalone page is missing V20 workbench asset'}
if(-not $pageResponse.Content.Contains('20260809-curve-export-r6')){throw 'standalone page is missing curve export revision'}
$schedule = Get-HttpJson 'http://127.0.0.1:8093/api/si-v20/schedule'
if(-not $schedule.ok -or -not $schedule.schedule.schedule_id){throw 'V20 production schedule schema was not initialized'}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskRegistrar | Out-Null
$scheduleTask = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20ScheduledShadowPrediction' -ErrorAction Stop
if($scheduleTask.Settings.MultipleInstances.ToString() -ne 'IgnoreNew'){throw 'schedule task overlap policy is not IgnoreNew'}
$listener8768After = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if(-not $listener8768After){throw '8768 is not listening after deployment'}
if([int]$listener8768After.OwningProcess -ne [int]$listener8768Before.OwningProcess){throw '8768 PID changed unexpectedly'}
$protectedAfter = @{}
foreach($port in @(8094,8770,11434)){
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $protectedAfter[[string]$port] = [int]$listener.OwningProcess
    if($protectedAfter[[string]$port] -ne $protectedBefore[[string]$port]){throw "protected port $port PID changed unexpectedly"}
}
[ordered]@{
    schema='ops.si-v20-workbench-8093.fast-deploy.v1'
    deployed_at=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    backup=$backup
    installed=$installed
    guard_restored=$true
    port_8093_listening=$true
    protected_8768_pid=$listener8768After.OwningProcess
    candidate_count=@($status.candidate_targets).Count
    recommended_target=$status.recommended_target.meltno
    standalone_page=$true
    schedule_id=$schedule.schedule.schedule_id
    schedule_cadence_minutes=$schedule.schedule.cadence_minutes
    schedule_task_state=$scheduleTask.State.ToString()
    schedule_task_overlap=$scheduleTask.Settings.MultipleInstances.ToString()
    protected_pids=$protectedAfter
} | ConvertTo-Json -Depth 6
