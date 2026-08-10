$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$frontend = Join-Path $root '高炉前端数据'
$backend = Join-Path $frontend '智能助手\backend'
$assets = Join-Path $frontend 'assets'
$server = Join-Path $backend 'ollama_proxy_server.py'
$module = Join-Path $backend 'si_v20_shadow.py'
$standalonePage = Join-Path $frontend 'si_v20_workbench.html'
$standaloneAsset = Join-Path $assets 'bf-si-v20-workbench.js'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$guardConfig = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$restart8094 = Join-Path $root 'tools\restart_22012_8094_preview.ps1'
$python = 'C:\Program Files\Python311\python.exe'
$tempRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$uploadedServer = Join-Path $tempRoot 'ollama_proxy_server.py'
$uploadedModule = Join-Path $tempRoot 'si_v20_shadow.py'
$uploadedPage = Join-Path $tempRoot 'si_v20_workbench.html'
$uploadedAsset = Join-Path $tempRoot 'bf-si-v20-workbench.js'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\si_v20_fullpage_20260808\$stamp"

function Wait-ServiceState { param([string]$Name,[string]$State,[int]$TimeoutSeconds=60)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds); do { if((Get-Service -Name $Name).Status.ToString() -eq $State){return}; Start-Sleep -Milliseconds 300 } while([DateTime]::UtcNow -lt $deadline); throw "$Name did not reach $State" }
function Wait-PortState { param([int]$Port,[bool]$Listening,[int]$TimeoutSeconds=90)
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds); do { $found=[bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1); if($found -eq $Listening){return}; Start-Sleep -Milliseconds 300 } while([DateTime]::UtcNow -lt $deadline); throw "port $Port did not reach listening=$Listening" }
function Install-AtomicFile { param([string]$Source,[string]$Target); $tmp="$Target.si_v20_installing"; Copy-Item -LiteralPath $Source -Destination $tmp -Force; Move-Item -LiteralPath $tmp -Destination $Target -Force }
function Backup-File { param([string]$Source,[string]$Name); if(Test-Path -LiteralPath $Source -PathType Leaf){Copy-Item -LiteralPath $Source -Destination (Join-Path $backup $Name) -Force; return $true}; return $false }
function Restore-File { param([string]$Name,[string]$Target); $source=Join-Path $backup $Name; if(Test-Path -LiteralPath $source -PathType Leaf){Install-AtomicFile $source $Target} }
function Get-JsonRetry { param([string]$Uri,[int]$Attempts=8); $last=$null; for($i=1;$i -le $Attempts;$i++){try{return Invoke-RestMethod -UseBasicParsing -Uri $Uri -TimeoutSec 30}catch{$last=$_;Start-Sleep -Seconds 2}}; throw $last }

foreach($path in @($python,$manager,$guardConfig,$restart8094,$uploadedServer,$uploadedModule,$uploadedPage,$uploadedAsset)){if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw "required file missing: $path"}}
& $python -X utf8 -m py_compile $uploadedServer $uploadedModule
if($LASTEXITCODE -ne 0){throw 'staged V20 Python syntax check failed'}
$service=Get-Service -Name BFV4PreviewProxy8093 -ErrorAction Stop
if($service.Status.ToString() -ne 'Running'){throw '8093 guard must be running before deployment'}
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$serverExisted=Backup-File $server 'ollama_proxy_server.py'
$moduleExisted=Backup-File $module 'si_v20_shadow.py'
$pageExisted=Backup-File $standalonePage 'si_v20_workbench.html'
$assetExisted=Backup-File $standaloneAsset 'bf-si-v20-workbench.js'
$installed=$false;$guardRestored=$false
try{
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState 'BFV4PreviewProxy8093' 'Stopped' 45; Wait-PortState 8093 $false 45
    Install-AtomicFile $uploadedServer $server
    Install-AtomicFile $uploadedModule $module
    Install-AtomicFile $uploadedPage $standalonePage
    Install-AtomicFile $uploadedAsset $standaloneAsset
    $installed=$true
}catch{
    if($serverExisted){Restore-File 'ollama_proxy_server.py' $server};if($moduleExisted){Restore-File 'si_v20_shadow.py' $module};if($pageExisted){Restore-File 'si_v20_workbench.html' $standalonePage};if($assetExisted){Restore-File 'bf-si-v20-workbench.js' $standaloneAsset};throw
}finally{
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig | Out-Null
    Wait-ServiceState 'BFV4PreviewProxy8093' 'Running' 60; Wait-PortState 8093 $true 90; $guardRestored=$true
}
try{
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    if($LASTEXITCODE -ne 0){throw '8094 managed restart failed'}
    $status8093=Get-JsonRetry 'http://127.0.0.1:8093/api/si-v20/status?limit=12'
    $status8094=Get-JsonRetry 'http://127.0.0.1:8094/api/si-v20/status?limit=12'
    if(-not $status8093.ok -or -not $status8094.ok){throw 'V20 status API failed'}
    if(-not ($status8093.PSObject.Properties.Name -contains 'candidate_targets') -or -not ($status8094.PSObject.Properties.Name -contains 'candidate_targets')){throw 'candidate_targets missing from status API'}
    $page8093=Get-JsonRetry 'http://127.0.0.1:8093/si_v20_workbench.html';$page8094=Get-JsonRetry 'http://127.0.0.1:8094/si_v20_workbench.html'
    if($page8093 -isnot [string]){$page8093=''};if($page8094 -isnot [string]){$page8094=''}
}catch{
    if($serverExisted){Restore-File 'ollama_proxy_server.py' $server};if($moduleExisted){Restore-File 'si_v20_shadow.py' $module};if($pageExisted){Restore-File 'si_v20_workbench.html' $standalonePage};if($assetExisted){Restore-File 'bf-si-v20-workbench.js' $standaloneAsset}
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action restart -ConfigPath $guardConfig | Out-Null
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094 | Out-Null
    throw
}
[ordered]@{schema='ops.si-v20-fullpage.deploy.v1';deployed_at=(Get-Date).ToString('yyyy-MM-dd HH:mm:ss');backup=$backup;installed=$installed;guard_restored=$guardRestored;status_8093=$status8093;status_8094=$status8094;standalone_page_8093=$true;standalone_page_8094=$true} | ConvertTo-Json -Depth 8
