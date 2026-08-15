[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Requirement = 'REQ-8093-OVERVIEW-SI24H-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Frontend = Join-Path $Root '高炉前端数据'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\REQ-8093-OVERVIEW-SI24H-20260811'
$Page8093 = Join-Path $Frontend 'frontend_dashboard_v3.server.html'
$Page8094 = Join-Path $Frontend 'frontend_dashboard_v3.8094_preview.server.html'
$MainAsset = Join-Path $Frontend 'assets\build\dashboard-main-DaGlW2vU.js'
$Stage8093 = Join-Path $Stage 'frontend_dashboard_v3.server.html'
$Stage8094 = Join-Path $Stage 'frontend_dashboard_v3.8094_preview.server.html'
$StageMain = Join-Path $Stage 'dashboard-main-DaGlW2vU.js'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$Config = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root "backups\overview_si24h_20260811\$Stamp"
$Expected = @{
    $Stage8093 = '4037CF1DB5254E27481850418247198CCD8221A81D21B21167DD903581109282'
    $Stage8094 = '889C32792785CF97947D7F45B9C6FDC94099A4994AC84E08231BE18D2B0265A2'
    $StageMain = '53076F6E22F84B5E065FD754DA976CC5F4CFABC34356F5C9E36E6EB6F70374FD'
}
$Baseline = @{
    $Page8093 = 'C2B94C72568D21EBDEE5D823796B5CC7AAA272A7A9B5ECB1BCDC6125E64B0529'
    $Page8094 = '30B21945EB0BAE4F17E5989C67EB395BD38A11BA4CF451E14FEAA9C0243DABB8'
}

function Get-Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Get-Listener([int]$Port) { $item = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($item) { [int]$item.OwningProcess } else { $null } }
function Wait-Port([int]$Port, [bool]$ExpectedState) { $until = [DateTime]::UtcNow.AddSeconds(75); do { if (($null -ne (Get-Listener $Port)) -eq $ExpectedState) { return }; Start-Sleep -Milliseconds 250 } while ([DateTime]::UtcNow -lt $until); throw "Port $Port listening=$ExpectedState timeout" }
function Install-Atomic([string]$Source, [string]$Target) { $temp = "$Target.$Stamp.tmp"; Copy-Item -LiteralPath $Source -Destination $temp -Force; Move-Item -LiteralPath $temp -Destination $Target -Force }
function Get-Page([int]$Port) { $last = $null; for ($i=0; $i -lt 8; $i++) { try { return Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?si24h=$Stamp#overview" -TimeoutSec 20 } catch { $last = $_; Start-Sleep -Seconds 1 } }; throw $last }

foreach ($path in @($Pwsh, $Manager, $Config, $Page8093, $Page8094, $Stage8093, $Stage8094, $StageMain)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" } }
foreach ($entry in $Expected.GetEnumerator()) { if ((Get-Hash $entry.Key) -ne $entry.Value) { throw "Stage hash mismatch: $($entry.Key)" } }
foreach ($entry in $Baseline.GetEnumerator()) { if ((Get-Hash $entry.Key) -ne $entry.Value) { throw "Production baseline mismatch: $($entry.Key)" } }
if (-not ([IO.File]::ReadAllText($Stage8094, [Text.Encoding]::UTF8).Contains($Requirement))) { throw '8094 staged marker missing.' }
$MainText = [IO.File]::ReadAllText($StageMain, [Text.Encoding]::UTF8)
if (-not $MainText.Contains('hourly-table?limit=24') -or -not $MainText.Contains('每小时Si预测')) { throw '8093 bundle contract missing.' }

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Locked = $false
$GuardPaused = $false
$GuardRestored = $false
$Rollback = $false
$Installed = $false
$ProtectedBefore = [ordered]@{}
foreach ($port in @(8094,8768,8770,5432,11434)) { $ProtectedBefore[[string]$port] = Get-Listener $port; if (-not $ProtectedBefore[[string]$port]) { throw "Protected port missing: $port" } }
$Old8093 = Get-Listener 8093
if (-not $Old8093) { throw '8093 is not listening before deployment.' }

try {
    $Locked = $Mutex.WaitOne(0)
    if (-not $Locked) { throw 'Deployment mutex is busy.' }
    New-Item -ItemType Directory -Path $Backup -Force | Out-Null
    Copy-Item -LiteralPath $Page8093 -Destination (Join-Path $Backup 'frontend_dashboard_v3.server.html') -Force
    Copy-Item -LiteralPath $Page8094 -Destination (Join-Path $Backup 'frontend_dashboard_v3.8094_preview.server.html') -Force
    if (Test-Path -LiteralPath $MainAsset) { Copy-Item -LiteralPath $MainAsset -Destination (Join-Path $Backup 'dashboard-main-DaGlW2vU.js') -Force }

    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $Config | Out-Null
    Wait-Port 8093 $false
    $GuardPaused = $true
    foreach ($port in $ProtectedBefore.Keys) { if ((Get-Listener ([int]$port)) -ne $ProtectedBefore[$port]) { throw "Protected PID changed before install: $port" } }

    Install-Atomic $Stage8093 $Page8093
    Install-Atomic $Stage8094 $Page8094
    Install-Atomic $StageMain $MainAsset
    $Installed = $true
}
catch {
    $Failure = $_
    if ($Installed) {
        Install-Atomic (Join-Path $Backup 'frontend_dashboard_v3.server.html') $Page8093
        Install-Atomic (Join-Path $Backup 'frontend_dashboard_v3.8094_preview.server.html') $Page8094
        if (Test-Path -LiteralPath (Join-Path $Backup 'dashboard-main-DaGlW2vU.js')) { Install-Atomic (Join-Path $Backup 'dashboard-main-DaGlW2vU.js') $MainAsset }
        elseif (Test-Path -LiteralPath $MainAsset) { Remove-Item -LiteralPath $MainAsset -Force }
        $Rollback = $true
    }
    throw $Failure
}
finally {
    if ($GuardPaused) {
        & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $Config | Out-Null
        Wait-Port 8093 $true
        $GuardRestored = $true
    }
    if ($Locked) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}

$Http8093 = Get-Page 8093
$Http8094 = Get-Page 8094
if ($Http8093.StatusCode -ne 200 -or $Http8094.StatusCode -ne 200) { throw 'Dashboard HTTP verification failed.' }
if (-not ([string]$Http8093.Content).Contains('dashboard-main-DaGlW2vU.js')) { throw '8093 new bundle reference is not served.' }
if (-not ([string]$Http8094.Content).Contains($Requirement)) { throw '8094 Si24h marker is not served.' }
foreach ($entry in @{$Page8093=$Expected[$Stage8093];$Page8094=$Expected[$Stage8094];$MainAsset=$Expected[$StageMain]}.GetEnumerator()) { if ((Get-Hash $entry.Key) -ne $entry.Value) { throw "Installed hash mismatch: $($entry.Key)" } }
$ProtectedAfter = [ordered]@{}
foreach ($port in $ProtectedBefore.Keys) { $ProtectedAfter[$port] = Get-Listener ([int]$port); if ($ProtectedAfter[$port] -ne $ProtectedBefore[$port]) { throw "Protected PID changed after install: $port" } }

[ordered]@{ ok=$true; requirement_id=$Requirement; backup=$Backup; guard_paused=$GuardPaused; guard_restored=$GuardRestored; rollback_applied=$Rollback; old_8093_pid=$Old8093; new_8093_pid=Get-Listener 8093; protected_before=$ProtectedBefore; protected_after=$ProtectedAfter; http_8093=[int]$Http8093.StatusCode; http_8094=[int]$Http8094.StatusCode; installed_hashes=[ordered]@{page8093=Get-Hash $Page8093;page8094=Get-Hash $Page8094;main=Get-Hash $MainAsset} } | ConvertTo-Json -Depth 8
