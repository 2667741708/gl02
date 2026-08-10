$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# ASCII-only remote script: discover the V4 project instead of embedding Chinese paths.
$project = @(Get-ChildItem -LiteralPath 'F:\' -Recurse -File -Filter 'frontend_dashboard_v3.server.html' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match 'V4_8093_PREVIEW' -and $_.FullName -notmatch '\\backups\\|\\logs\\|\\tmp\\' })
if ($project.Count -ne 1) { throw "expected one V4 8093 frontend, found $($project.Count)" }
$frontend = Split-Path -Parent $project[0].FullName
$root = Split-Path -Parent $frontend
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$config = @(Get-ChildItem -LiteralPath (Join-Path $root 'tools') -Recurse -File -Filter '22012_BFV4PreviewProxy8093.json' | Select-Object -First 1)
$python = 'C:\Program Files\Python311\python.exe'
$service = 'BFV4PreviewProxy8093'
$guardPath = '\BlastFurnaceServices\'
$guardName = 'BFV4PreviewProxy8093HealthCheck'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\bf_heat_query_v2_stage'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "logs\deploy_backups\8093_heat_query_v2_$stamp"

$mainProxy = @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'ollama_proxy_server.py' |
    Where-Object { $_.FullName -notmatch 'standalone_heat_dashboard_8891|backups|logs|tmp' } | Select-Object -First 1)
$mainStore = @(Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'heat_performance_quality.py' |
    Where-Object { $_.FullName -notmatch 'standalone_heat_dashboard_8891|backups|logs|tmp' } | Select-Object -First 1)
$heatService = Join-Path $root 'db_dashboard\heat_service.py'
$standaloneStore = @(Get-ChildItem -LiteralPath $standalone -Recurse -File -Filter 'heat_performance_quality.py' |
    Where-Object { $_.FullName -notmatch 'backups|logs|tmp' } | Select-Object -First 1)
$newAsset = Join-Path (Join-Path $frontend 'assets') 'bf-heat-performance-quality-8093-query-v2.js'
foreach ($p in @($manager, $config[0].FullName, $mainProxy[0].FullName, $mainStore[0].FullName, $heatService, $standaloneStore[0].FullName, $project[0].FullName)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "required target missing: $p" }
}

function ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object { $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$' })[0]
    if ($line -and $line -match 'LISTENING\s+(\d+)\s*$') { return [int]$matches[1] }
    return $null
}
function WaitState([string]$Name, [string]$State) {
    $until = [DateTime]::UtcNow.AddSeconds(60)
    do { if ((Get-Service -Name $Name).Status.ToString() -eq $State) { return }; Start-Sleep -Milliseconds 250 } while ([DateTime]::UtcNow -lt $until)
    throw "$Name did not reach $State"
}
function WaitPort([int]$Port, [bool]$Listening) {
    $until = [DateTime]::UtcNow.AddSeconds(75)
    do { if (([bool](ListenerPid $Port)) -eq $Listening) { return }; Start-Sleep -Milliseconds 250 } while ([DateTime]::UtcNow -lt $until)
    throw "port $Port listening=$Listening timeout"
}

$targets = @(
    [pscustomobject]@{ Name='proxy'; Target=$mainProxy[0].FullName; Stage=(Join-Path $stage 'ollama_proxy_server.py') },
    [pscustomobject]@{ Name='store-main'; Target=$mainStore[0].FullName; Stage=(Join-Path $stage 'heat_performance_quality.py') },
    [pscustomobject]@{ Name='heat-service'; Target=$heatService; Stage=(Join-Path $stage 'heat_service.py') },
    [pscustomobject]@{ Name='store-standalone'; Target=$standaloneStore[0].FullName; Stage=(Join-Path $stage 'heat_performance_quality.py') },
    [pscustomobject]@{ Name='html'; Target=$project[0].FullName; Stage=(Join-Path $stage 'frontend_dashboard_v3.server.html') },
    [pscustomobject]@{ Name='query-asset'; Target=$newAsset; Stage=(Join-Path $stage 'bf-heat-performance-quality-8093-query-v2.js') }
)
foreach ($item in $targets) {
    if (-not (Test-Path -LiteralPath $item.Stage -PathType Leaf)) { throw "staged file missing: $($item.Stage)" }
}
& $python -m py_compile (Join-Path $stage 'ollama_proxy_server.py') (Join-Path $stage 'heat_performance_quality.py') (Join-Path $stage 'heat_service.py')
if ($LASTEXITCODE -ne 0) { throw 'staged Python compile failed' }

$protected = @{}
foreach ($port in @(8768,8094,8770)) { $protected[$port] = ListenerPid $port }
$before8093 = ListenerPid 8093
$manifest = @{}
New-Item -ItemType Directory -Path $backup -Force | Out-Null
foreach ($item in $targets) {
    $safe = ($item.Name + '_' + ([IO.Path]::GetFileName($item.Target))) -replace '[^A-Za-z0-9_.-]', '_'
    $dest = Join-Path $backup $safe
    $exists = Test-Path -LiteralPath $item.Target -PathType Leaf
    if ($exists) { Copy-Item -LiteralPath $item.Target -Destination $dest -Force }
    $manifest[$item.Target] = [pscustomobject]@{ Exists=$exists; Backup=$dest }
}

$guardPaused = $false
$serviceStopped = $false
$deployed = $false
try {
    Disable-ScheduledTask -TaskPath $guardPath -TaskName $guardName -ErrorAction SilentlyContinue | Out-Null
    Stop-ScheduledTask -TaskPath $guardPath -TaskName $guardName -ErrorAction SilentlyContinue
    $guardPaused = $true
    & $manager -Action stop -ConfigPath $config[0].FullName | Out-Null
    WaitState $service 'Stopped'
    WaitPort 8093 $false
    $serviceStopped = $true
    foreach ($port in @(8768,8094,8770)) { if ((ListenerPid $port) -ne $protected[$port]) { throw "protected port $port changed before deploy" } }
    foreach ($item in $targets) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $item.Target) -Force | Out-Null
        $tmp = "$($item.Target).deploy_$stamp"
        Copy-Item -LiteralPath $item.Stage -Destination $tmp -Force
        Move-Item -LiteralPath $tmp -Destination $item.Target -Force
    }
    $deployed = $true
    & $python -m py_compile $mainProxy[0].FullName $mainStore[0].FullName $heatService $standaloneStore[0].FullName
    if ($LASTEXITCODE -ne 0) { throw 'deployed Python compile failed' }
    & $manager -Action start -ConfigPath $config[0].FullName | Out-Null
    WaitState $service 'Running'
    WaitPort 8093 $true
    $serviceStopped = $false
    $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=heat-query-$stamp" -TimeoutSec 30
    if ([int]$page.StatusCode -ne 200 -or $page.Content -notmatch 'bf-heat-performance-quality-8093-query-v2') { throw '8093 query-v2 asset marker missing' }
    $api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/heat-performance-quality?limit=5&has_samples=1&t=$stamp" -TimeoutSec 30
    $rich = @($api.items | Where-Object { @($_.sample_details).Count -gt 0 -and @($_.output_details).Count -gt 0 })
    if (-not $api.ok -or $rich.Count -lt 1) { throw '8093 API did not return a heat with samples and output segments' }
} catch {
    $err = $_
    try {
        if ((Get-Service -Name $service).Status.ToString() -ne 'Stopped') { & $manager -Action stop -ConfigPath $config[0].FullName | Out-Null; WaitState $service 'Stopped'; WaitPort 8093 $false }
        foreach ($item in $targets) {
            $entry = $manifest[$item.Target]
            if ($entry.Exists) { Copy-Item -LiteralPath $entry.Backup -Destination $item.Target -Force } elseif (Test-Path -LiteralPath $item.Target) { Remove-Item -LiteralPath $item.Target -Force }
        }
    } finally {
        Enable-ScheduledTask -TaskPath $guardPath -TaskName $guardName -ErrorAction SilentlyContinue | Out-Null
        & $manager -Action start -ConfigPath $config[0].FullName | Out-Null
        WaitState $service 'Running'
        WaitPort 8093 $true
    }
    throw $err
}

Enable-ScheduledTask -TaskPath $guardPath -TaskName $guardName -ErrorAction SilentlyContinue | Out-Null
foreach ($port in @(8768,8094,8770)) { if ((ListenerPid $port) -ne $protected[$port]) { throw "protected PID changed on $port" } }
$finalApi = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/heat-performance-quality?limit=3&t=$stamp" -TimeoutSec 30
[ordered]@{
    schema='ops.8093.heat-query.v2'
    requirement_id='REQ-8093-HEAT-PERFORMANCE-QUALITY-QUERY-20260807'
    backup_root=$backup
    guard_paused=$guardPaused
    guard_restored=((Get-ScheduledTask -TaskPath $guardPath -TaskName $guardName -ErrorAction SilentlyContinue).State.ToString() -ne 'Disabled')
    service_state=(Get-Service -Name $service).Status.ToString()
    listener_8093_before=$before8093
    listener_8093_after=(ListenerPid 8093)
    api_count=@($finalApi.items).Count
    latest_meltno=@($finalApi.items)[0].meltno
    protected_pids=@{ p8768=$protected[8768]; p8094=$protected[8094]; p8770=$protected[8770] }
} | ConvertTo-Json -Depth 6
