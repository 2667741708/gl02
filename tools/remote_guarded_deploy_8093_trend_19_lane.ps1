$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$target = Join-Path $frontend "frontend_dashboard_v3.server.html"
$stage = "C:\Users\Administrator\AppData\Local\Temp\frontend_dashboard_v3.trend19.html"
$expectedBeforeHash = "D78A9A7289FB71BA5381A069E1C7E6B086D148CD62090A5EC71FA199D8C5490A"
$html8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$sharedAdapter = Join-Path $frontend "assets\bf3d-furnace-body-billboard-adapter.js"
$camera8094 = Join-Path $frontend "assets\bf3d-surface-camera-guard-8094.js"
$manager = Join-Path $root "tools\manage_22012_managed_services.ps1"
$config = Join-Path $root "tools\service_configs\22012_BFV4PreviewProxy8093.json"
$python = "C:\Program Files\Python311\python.exe"
$serviceName = "BFV4PreviewProxy8093"
$wsServiceName = "BFV4PreviewWs8768"
$taskPath = "\BlastFurnaceServices\"
$taskName8094 = "V3AutoPreviewProxy8094"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8093_trend_19_lane_$stamp"
$backupFile = Join-Path $backup "frontend_dashboard_v3.server.html"
$tempTarget = Join-Path $frontend "frontend_dashboard_v3.server.html.trend19.tmp"
$replaceBackup = Join-Path $backup "frontend_dashboard_v3.server.replace.bak"
$guardPaused = $false
$guardRestored = $false
$installed = $false

function Wait-ServiceState {
    param([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 45)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $DesiredState) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState"
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 45)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

foreach ($path in @($target, $stage, $html8094, $sharedAdapter, $camera8094, $manager, $config, $python)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required deployment file is missing: $path" }
}
$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
if ($beforeHash -ne $expectedBeforeHash) { throw "8093 changed after preflight: $beforeHash" }
$stageText = Get-Content -LiteralPath $stage -Raw -Encoding UTF8
foreach ($marker in @(
    "REQ-TREND-19-LANE-MERGE-20260807",
    "19个核心变量趋势与预测",
    "const TREND_PREDICT_IDS=['P_top','P_top_gas_A','P_top_gas_B','P_top_gas_C','P_top_gas_D','T_top','T_top_A','T_top_B','T_top_C','T_top_D','Q_blast','P_blast_cold','P_blast','T_blast','PI','DP_total','DP_upper','DP_lower','GasUtil']",
    "target_ids: TREND_PREDICT_IDS",
    "TREND_PREDICT_IDS.includes(id)"
)) {
    if (-not $stageText.Contains($marker)) { throw "Staged 8093 payload marker is missing: $marker" }
}

$serviceBefore = Get-Service -Name $serviceName -ErrorAction Stop
$wsBefore = Get-Service -Name $wsServiceName -ErrorAction Stop
$taskBefore = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName8094 -ErrorAction Stop
if ($serviceBefore.Status.ToString() -ne "Running" -or $wsBefore.Status.ToString() -ne "Running" -or $taskBefore.State.ToString() -ne "Running") {
    throw "8093 guard, 8768 service, and 8094 task must be running before deployment"
}
$portsBefore = [ordered]@{}
foreach ($port in 8093,8094,8768,8770,11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
    $portsBefore[[string]$port] = [int]$listener.OwningProcess
}
$protectedBefore = [ordered]@{
    html8094 = (Get-FileHash -Algorithm SHA256 -LiteralPath $html8094).Hash
    sharedAdapter = (Get-FileHash -Algorithm SHA256 -LiteralPath $sharedAdapter).Hash
    camera8094 = (Get-FileHash -Algorithm SHA256 -LiteralPath $camera8094).Hash
}
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $target -Destination $backupFile -Force

try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $config | Out-Null
    Wait-ServiceState -Name $serviceName -DesiredState "Stopped"
    Wait-PortState -Port 8093 -Listening $false
    $guardPaused = $true
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue)) { throw "8768 stopped while pausing 8093 guard" }

    Copy-Item -LiteralPath $stage -Destination $tempTarget -Force
    [IO.File]::Replace($tempTarget, $target, $replaceBackup, $true)
    $installed = $true
}
catch {
    if ($installed -and (Test-Path -LiteralPath $backupFile -PathType Leaf)) {
        Copy-Item -LiteralPath $backupFile -Destination $target -Force
    }
    throw
}
finally {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    Wait-ServiceState -Name $serviceName -DesiredState "Running"
    $guardRestored = $true
}

try {
    Wait-PortState -Port 8093 -Listening $true
    $cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri "http://127.0.0.1:8093/frontend_dashboard_v3.server.html?trend19=$cacheBust#trend"
    if ($response.StatusCode -ne 200 -or -not $response.Content.Contains("REQ-TREND-19-LANE-MERGE-20260807") -or -not $response.Content.Contains("19个核心变量趋势与预测")) {
        throw "8093 did not serve the merged trend page after guard restore"
    }
    $afterPorts = [ordered]@{}
    foreach ($port in 8093,8094,8768,8770,11434) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -First 1
        $afterPorts[[string]$port] = [int]$listener.OwningProcess
        if ($port -ne 8093 -and $afterPorts[[string]$port] -ne $portsBefore[[string]$port]) { throw "Protected PID changed on port $port" }
    }
    $protectedAfter = [ordered]@{
        html8094 = (Get-FileHash -Algorithm SHA256 -LiteralPath $html8094).Hash
        sharedAdapter = (Get-FileHash -Algorithm SHA256 -LiteralPath $sharedAdapter).Hash
        camera8094 = (Get-FileHash -Algorithm SHA256 -LiteralPath $camera8094).Hash
    }
    foreach ($name in $protectedBefore.Keys) {
        if ($protectedAfter[$name] -ne $protectedBefore[$name]) { throw "Protected hash changed: $name" }
    }
    [ordered]@{
        ok = $true
        requirement = "REQ-TREND-19-LANE-MERGE-20260807"
        backup = $backup
        guard_paused = $guardPaused
        guard_restored = $guardRestored
        http_8093 = [int]$response.StatusCode
        before_hash = $beforeHash
        after_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
        ports_before = $portsBefore
        ports_after = $afterPorts
        protected_8094_hashes_unchanged = $true
        restart_8093_performed = $true
    } | ConvertTo-Json -Depth 6
}
finally {
    Remove-Item -LiteralPath $tempTarget -Force -ErrorAction SilentlyContinue
}
