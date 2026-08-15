$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '高炉前端数据\furnace-rule-admin.html'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\furnace-rule-admin.login.html'
$BackendTarget = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$BackendStage = 'C:\Users\Administrator\AppData\Local\Temp\ollama_proxy_server.admin-login.py'
$ExpectedHash = '5BA2853B7ACEA17F23A8170819D4CB22A5E017E2D23CF92ED31C636C19E212CA'
$ExpectedBackendHash = '3D665E5A4BF75050E1B7C2EBEFCAF77786F4F5CDDB2061E936A0BD0D21E2A03E'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$Config = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Ports = @(8094,8768,8770,5432,11434)
function Listener([int]$Port) { $r=Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1; if($r){[int]$r.OwningProcess}else{$null} }
function Protected { $m=[ordered]@{}; foreach($p in $Ports){$m[[string]$p]=Listener $p}; $m }
function Wait8093([bool]$Listening){$d=(Get-Date).AddSeconds(60);do{if([bool](Listener 8093)-eq $Listening){return};Start-Sleep -Milliseconds 250}while((Get-Date)-lt$d);throw "8093 listening=$Listening timeout"}
if(-not(Test-Path -LiteralPath $Stage -PathType Leaf)){[pscustomobject]@{ok=$true;mode='preflight';target_hash=(Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash;backend_hash=(Get-FileHash -LiteralPath $BackendTarget -Algorithm SHA256).Hash;listener_8093=Listener 8093;protected=Protected}|ConvertTo-Json -Depth 4;exit 0}
$Current=(Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
if(-not $ExpectedHash -or $Current-ne$ExpectedHash){throw "Unreviewed target hash: $Current"}
$CurrentBackend=(Get-FileHash -LiteralPath $BackendTarget -Algorithm SHA256).Hash
if(-not $ExpectedBackendHash -or $CurrentBackend-ne$ExpectedBackendHash){throw "Unreviewed backend hash: $CurrentBackend"}
$Text=Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
foreach($Marker in @('管理员登录','loginForm','/api/auth/login','historyStart','/api/admin/furnace-rules/history','来源实际值/窗口统计')){if(-not$Text.Contains($Marker)){throw "Missing marker: $Marker"}}
$Before=Protected;foreach($p in $Before.Keys){if(-not$Before[$p]){throw "Protected port $p missing"}}
$Old=Listener 8093;$Stamp=Get-Date -Format 'yyyyMMdd_HHmmss';$BackupRoot=Join-Path $Root "backups\8093_admin_login_page_$Stamp";$Backup=Join-Path $BackupRoot 'furnace-rule-admin.html';$BackendBackup=Join-Path $BackupRoot 'ollama_proxy_server.py';New-Item -ItemType Directory -Path $BackupRoot -Force|Out-Null;Copy-Item -LiteralPath $Target -Destination $Backup;Copy-Item -LiteralPath $BackendTarget -Destination $BackendBackup
$Mutex=[Threading.Mutex]::new($false,'Global\BFV4PreviewProxy8093Deployment');$Acquired=$false;$Paused=$false;$Restored=$false;$Rollback=$false
try{$Acquired=$Mutex.WaitOne(0);if(-not$Acquired){throw '8093 deployment mutex is busy'};&$Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $Config|Out-Null;if($LASTEXITCODE-ne0){throw 'stop failed'};Wait8093 $false;$Paused=$true;$Temp="$Target.deploying-$Stamp";$BackendTemp="$BackendTarget.deploying-$Stamp";Copy-Item -LiteralPath $Stage -Destination $Temp -Force;Copy-Item -LiteralPath $BackendStage -Destination $BackendTemp -Force;Move-Item -LiteralPath $Temp -Destination $Target -Force;Move-Item -LiteralPath $BackendTemp -Destination $BackendTarget -Force;&$Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $Config|Out-Null;if($LASTEXITCODE-ne0){throw 'start failed'};Wait8093 $true;$Restored=$true;$New=Listener 8093
$Page=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/furnace-rule-admin.html?cb=$Stamp" -TimeoutSec 30;if($Page.StatusCode-ne200){throw 'admin page HTTP failed'};foreach($Marker in @('管理员登录','loginForm','historyStart','/api/admin/furnace-rules/history','来源实际值/窗口统计')){if(-not$Page.Content.Contains($Marker)){throw "HTTP marker missing: $Marker"}}
$LiveConfig=Get-Content -LiteralPath $Config -Raw -Encoding UTF8|ConvertFrom-Json;$Username=[string]$LiveConfig.env.BF_LOGIN_USERS;$Key=($Username-replace'[^A-Za-z0-9]+','_').ToUpper().Trim('_');$Password=[string]$LiveConfig.env."BF_LOGIN_${Key}_PASSWORD";$Session=New-Object Microsoft.PowerShell.Commands.WebRequestSession;$Body=@{username=$Username;password=$Password}|ConvertTo-Json;$Login=Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8093/api/auth/login' -ContentType 'application/json' -Body $Body -WebSession $Session -TimeoutSec 20;if(-not$Login.ok){throw 'admin login failed'};$Start=(Get-Date).AddHours(-1).ToString('o');$End=(Get-Date).ToString('o');$History=Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/admin/furnace-rules/history?start=$([uri]::EscapeDataString($Start))&end=$([uri]::EscapeDataString($End))&limit=12" -WebSession $Session -TimeoutSec 30;if(-not$History.ok-or@($History.batches).Count-eq0){throw 'admin history API returned no batches'};$EvaluationId=@($History.batches)[0].id;$Full=Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/admin/furnace-rules/latest-full?evaluation_id=$EvaluationId" -WebSession $Session -TimeoutSec 30;if(-not$Full.ok-or@($Full.rules).Count-ne33){throw 'selected evaluation did not return 33 rules'}
$After=Protected;foreach($p in $Before.Keys){if($After[$p]-ne$Before[$p]){throw "Protected PID changed: $p"}};[pscustomobject]@{ok=$true;backup=$Backup;guard_paused=$Paused;guard_restored=$Restored;rollback_applied=$false;old_8093_pid=$Old;new_8093_pid=$New;http_8093=$Page.StatusCode;installed_hash=(Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash;protected_before=$Before;protected_after=$After}|ConvertTo-Json -Depth 5}
catch{$Failure=$_.Exception.Message;try{if(Listener 8093){&$Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $Config|Out-Null;Wait8093 $false};Copy-Item -LiteralPath $Backup -Destination $Target -Force;Copy-Item -LiteralPath $BackendBackup -Destination $BackendTarget -Force;$Rollback=$true}finally{&$Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $Config|Out-Null;Wait8093 $true;$Restored=$true};[pscustomobject]@{ok=$false;failure=$Failure;rollback_applied=$Rollback;guard_restored=$Restored}|ConvertTo-Json;throw $Failure}
finally{if($Acquired){$Mutex.ReleaseMutex()};$Mutex.Dispose();Remove-Item -LiteralPath $Stage -Force -ErrorAction SilentlyContinue}
