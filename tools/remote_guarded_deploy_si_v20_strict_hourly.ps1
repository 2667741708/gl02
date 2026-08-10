$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required'
}

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$frontend = Join-Path $root '高炉前端数据'
$backend = Join-Path $frontend '智能助手\backend'
$assets = Join-Path $frontend 'assets'
$models = Join-Path $backend 'models'
$abcService = Join-Path $root '自动诊断服务'
$toolsDir = Join-Path $root 'tools'
$manager = Join-Path $toolsDir 'manage_22012_managed_services.ps1'
$guardConfig = Join-Path $toolsDir 'service_configs\22012_BFV4PreviewProxy8093.json'
$restart8094 = Join-Path $toolsDir 'restart_22012_8094_preview.ps1'
$python = 'C:\Program Files\Python311\python.exe'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$temp = 'C:\Users\Administrator\AppData\Local\Temp'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\si_v20_strict_hourly_20260810\$stamp"

$installMap = [ordered]@{
    'si_v20_strict_ollama_proxy_server.py' = (Join-Path $backend 'ollama_proxy_server.py')
    'si_v20_strict_si_v20_shadow.py' = (Join-Path $backend 'si_v20_shadow.py')
    'si_v20_strict_context.py' = (Join-Path $backend 'si_v20_strict_context.py')
    'si_v20_strict_heat_performance_quality.py' = (Join-Path $backend 'heat_performance_quality.py')
    'si_v20_strict_context_lgbm_v1.json.gz' = (Join-Path $models 'si_v20_strict_context_lgbm_v1.json.gz')
    'si_v20_strict_workbench.html' = (Join-Path $frontend 'si_v20_workbench.html')
    'si_v20_strict_workbench.js' = (Join-Path $assets 'bf-si-v20-workbench.js')
    'si_v20_strict_abc_term_semantics.py' = (Join-Path $abcService 'abc_term_semantics.py')
    'run_si_v20_strict_hourly_dispatcher.py' = (Join-Path $toolsDir 'run_si_v20_strict_hourly_dispatcher.py')
    'run_22012_si_v20_strict_hourly.ps1' = (Join-Path $toolsDir 'run_22012_si_v20_strict_hourly.ps1')
    'register_22012_si_v20_strict_hourly_task.ps1' = (Join-Path $toolsDir 'register_22012_si_v20_strict_hourly_task.ps1')
    'restart_22012_8094_preview.ps1' = (Join-Path $toolsDir 'restart_22012_8094_preview.ps1')
}

function Wait-ServiceState { param([string]$Name,[string]$State,[int]$TimeoutSeconds=90)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do { if((Get-Service -Name $Name).Status.ToString() -eq $State){return}; Start-Sleep -Milliseconds 300 } while([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $State"
}
function Wait-Port { param([int]$Port,[bool]$Listening,[int]$TimeoutSeconds=120)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do { $found=[bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1); if($found -eq $Listening){return}; Start-Sleep -Milliseconds 400 } while([DateTime]::UtcNow -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}
function Install-Atomic { param([string]$Source,[string]$Target)
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    $pending = "$Target.strict_installing"
    Copy-Item -LiteralPath $Source -Destination $pending -Force
    Move-Item -LiteralPath $pending -Destination $Target -Force
}
function Get-JsonRetry { param([string]$Uri,[int]$Attempts=15)
    $last=$null
    for($i=0;$i -lt $Attempts;$i++){try{return Invoke-RestMethod -UseBasicParsing -Uri $Uri -TimeoutSec 25}catch{$last=$_;Start-Sleep -Seconds 2}}
    throw $last
}
function Test-IgnoreNewPolicy { param($Value)
    return @('IgnoreNew', '2') -contains [string]$Value
}

foreach($required in @($python,$pwsh,$manager,$guardConfig,$restart8094)){
    if(-not(Test-Path -LiteralPath $required -PathType Leaf)){throw "required file missing: $required"}
}
foreach($name in $installMap.Keys){
    $source = Join-Path $temp $name
    if(-not(Test-Path -LiteralPath $source -PathType Leaf)){throw "uploaded file missing: $source"}
}

& $python -X utf8 -m py_compile (Join-Path $temp 'si_v20_strict_ollama_proxy_server.py') (Join-Path $temp 'si_v20_strict_si_v20_shadow.py') (Join-Path $temp 'si_v20_strict_context.py') (Join-Path $temp 'si_v20_strict_heat_performance_quality.py') (Join-Path $temp 'si_v20_strict_abc_term_semantics.py') (Join-Path $temp 'run_si_v20_strict_hourly_dispatcher.py')
if($LASTEXITCODE -ne 0){throw 'staged strict-hourly Python syntax check failed'}

$protectedBefore=@{}
foreach($port in @(8768,8770,11434)){
    $listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $protectedBefore[[string]$port]=[int]$listener.OwningProcess
}
if((Get-Service -Name BFV4PreviewProxy8093).Status.ToString() -ne 'Running'){throw '8093 guard must be running before deployment'}
if(-not(Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue)){throw '8094 must be listening before deployment'}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
$backups=[ordered]@{}
foreach($name in $installMap.Keys){
    $target=$installMap[$name]
    $existed=Test-Path -LiteralPath $target -PathType Leaf
    $backups[$name]=$existed
    if($existed){Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name) -Force}
}

$installed=$false
try {
    & $pwsh -NoLogo -NoProfile -File $manager -Action stop -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState 'BFV4PreviewProxy8093' 'Stopped'
    Wait-Port 8093 $false
    foreach($name in $installMap.Keys){Install-Atomic (Join-Path $temp $name) $installMap[$name]}
    $installed=$true
} catch {
    foreach($name in $installMap.Keys){
        $target=$installMap[$name]
        $saved=Join-Path $backup $name
        if($backups[$name]){Install-Atomic $saved $target}elseif(Test-Path -LiteralPath $target -PathType Leaf){Remove-Item -LiteralPath $target -Force}
    }
    throw
} finally {
    & $pwsh -NoLogo -NoProfile -File $manager -Action start -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState 'BFV4PreviewProxy8093' 'Running'
    Wait-Port 8093 $true
}

try {
    & $pwsh -NoLogo -NoProfile -File $restart8094 | Out-Null
    if($LASTEXITCODE -ne 0){throw '8094 controlled restart failed'}
    Wait-Port 8094 $true
    $status8093=Get-JsonRetry 'http://127.0.0.1:8093/api/si-v20/strict-hourly/status'
    $status8094=Get-JsonRetry 'http://127.0.0.1:8094/api/si-v20/strict-hourly/status'
    if(-not $status8093.ok -or -not $status8094.ok){throw 'strict-hourly status API returned ok=false'}
    $hourlyTable8093=Get-JsonRetry 'http://127.0.0.1:8093/api/si-v20/hourly-table'
    $hourlyTable8094=Get-JsonRetry 'http://127.0.0.1:8094/api/si-v20/hourly-table'
    if(-not $hourlyTable8093.ok -or -not $hourlyTable8094.ok){throw 'hourly table API returned ok=false'}
    $page=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/si_v20_workbench.html?cb=20260810-hourly-table-r2' -TimeoutSec 30
    if(-not $page.Content.Contains('20260810-hourly-table-r2')){throw 'hourly-table workbench asset revision is missing'}
    & $pwsh -NoLogo -NoProfile -File (Join-Path $toolsDir 'register_22012_si_v20_strict_hourly_task.ps1') | Out-Null
    $strictTask=Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'SiV20StrictHourlyPrediction' -ErrorAction Stop
    if(-not (Test-IgnoreNewPolicy $strictTask.Settings.MultipleInstances)){throw 'strict task overlap policy is not IgnoreNew'}
} catch {
    foreach($name in $installMap.Keys){
        $target=$installMap[$name]
        $saved=Join-Path $backup $name
        if($backups[$name]){Install-Atomic $saved $target}elseif(Test-Path -LiteralPath $target -PathType Leaf){Remove-Item -LiteralPath $target -Force}
    }
    & $pwsh -NoLogo -NoProfile -File $manager -Action restart -ConfigPath $guardConfig | Out-Null
    & $pwsh -NoLogo -NoProfile -File $restart8094 | Out-Null
    throw
}

$protectedAfter=@{}
foreach($port in @(8768,8770,11434)){
    $listener=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $protectedAfter[[string]$port]=[int]$listener.OwningProcess
    if($protectedAfter[[string]$port] -ne $protectedBefore[[string]$port]){throw "protected port $port PID changed unexpectedly"}
}

[ordered]@{
    schema='ops.si-v20.strict-hourly-deploy.v1'
    deployed_at=(Get-Date).ToString('o')
    backup=$backup
    installed=$installed
    guard_restored=$true
    strict_task_state=$strictTask.State.ToString()
    strict_task_overlap=$strictTask.Settings.MultipleInstances.ToString()
    status_8093=$status8093
    status_8094=$status8094
    protected_pids=$protectedAfter
} | ConvertTo-Json -Depth 8
