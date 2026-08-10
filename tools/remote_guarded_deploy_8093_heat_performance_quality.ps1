$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$serviceName = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$guardTaskPath = '\BlastFurnaceServices\'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$syncTaskName = 'HeatPerformanceQualitySync'
$python = 'C:\Program Files\Python311\python.exe'
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp\bf_heat_performance_stage'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\8093_heat_performance_$stamp"

$files = @(
    @{ Root = $root; Relative = '高炉前端数据\智能助手\backend\ollama_proxy_server.py'; Stage = 'ollama_proxy_server.py'; Hash = '8F7F17B3CBC9B3F481714488BAC6A991A384F67D67974082FF153879D342AFF5' },
    @{ Root = $root; Relative = '高炉前端数据\智能助手\backend\heat_performance_quality.py'; Stage = 'heat_performance_quality.py'; Hash = 'DE481F17731F1FCAED5C0DC28AC087705C7B92716A82E09ABD0246154D1CC0EB' },
    @{ Root = $root; Relative = '高炉前端数据\frontend_dashboard_v3.server.html'; Stage = 'frontend_dashboard_v3.server.html'; Hash = '2A1E34BA326FCA2AABCC7F55231B0DD0ECD13654684132481BBB22A747BF40CC' },
    @{ Root = $root; Relative = '高炉前端数据\assets\bf-heat-performance-quality-8093.js'; Stage = 'bf-heat-performance-quality-8093.js'; Hash = '9ACC31494E3D79A50EF251B999BBBB5F674E1E0186F55E223E58E7C1D221A7A3' },
    @{ Root = $standalone; Relative = '高炉前端数据\智能助手\backend\heat_performance_quality.py'; Stage = 'heat_performance_quality.py'; Hash = 'DE481F17731F1FCAED5C0DC28AC087705C7B92716A82E09ABD0246154D1CC0EB' },
    @{ Root = $standalone; Relative = 'tools\sync_22012_heat_performance_quality.py'; Stage = 'sync_22012_heat_performance_quality.py'; Hash = 'BEF01456E57877A4842FB28C316D67C1C7E463A688F982192791D8431B6A48CB' },
    @{ Root = $standalone; Relative = 'tools\run_22012_heat_performance_sync.ps1'; Stage = 'run_22012_heat_performance_sync.ps1'; Hash = '970DAE922E75379E1F978DF6BC286F01F251A297A6BBB7F6C696D7168CA932A8' }
)

function Get-Listener([int]$Port, [bool]$Required = $true) {
    $line = @(netstat.exe -ano | Where-Object { $_ -match ":$Port\s" -and $_ -match "LISTENING\s+(\d+)\s*$" })[0]
    if (-not $line) {
        if ($Required) { throw "TCP $Port is not listening" }
        return $null
    }
    [void]($line -match "LISTENING\s+(\d+)\s*$")
    return [pscustomobject]@{ port = $Port; pid = [int]$matches[1] }
}

function Get-ListenerPid([int]$Port) {
    $listener = Get-Listener $Port $false
    if ($listener) { return [int]$listener.pid }
    return $null
}

function Wait-ServiceState([string]$Name, [string]$DesiredState, [int]$TimeoutSeconds = 60) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if ((Get-Service -Name $Name -ErrorAction Stop).Status.ToString() -eq $DesiredState) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "$Name did not reach $DesiredState"
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool]@(netstat.exe -ano | Where-Object { $_ -match ":$Port\s" -and $_ -match 'LISTENING' })
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "TCP $Port did not reach listening=$Listening"
}

function Install-File($item) {
    $target = Join-Path $item.Root $item.Relative
    $source = Join-Path $stageRoot $item.Stage
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    $temporary = "$target.deploy_$stamp"
    Copy-Item -LiteralPath $source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Restore-Files {
    foreach ($item in $files) {
        $target = Join-Path $item.Root $item.Relative
        $key = "$($item.Root)|$($item.Relative)"
        $entry = $manifest[$key]
        if ($entry.existed) {
            Copy-Item -LiteralPath $entry.backup -Destination $target -Force
        } elseif (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Force
        }
    }
}

foreach ($required in @($root, $standalone, $manager, $configPath, $python)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "missing required path: $required" }
}
foreach ($item in $files) {
    $stage = Join-Path $stageRoot $item.Stage
    if (-not (Test-Path -LiteralPath $stage -PathType Leaf)) { throw "missing staged file: $stage" }
    if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash -ne $item.Hash) { throw "staged hash mismatch: $($item.Stage)" }
}
& $python -m py_compile (Join-Path $stageRoot 'ollama_proxy_server.py') (Join-Path $stageRoot 'heat_performance_quality.py') (Join-Path $stageRoot 'sync_22012_heat_performance_quality.py')
if ($LASTEXITCODE -ne 0) { throw 'staged Python compile failed' }

$protectedBefore = @{}
foreach ($port in @(8768, 8094, 8770)) { $protectedBefore[$port] = Get-ListenerPid $port }
$listener8093Before = Get-Listener 8093 $false
$serviceStateBefore = (Get-Service -Name $serviceName).Status.ToString()
$existingSyncTask = Get-ScheduledTask -TaskPath $guardTaskPath -TaskName $syncTaskName -ErrorAction SilentlyContinue
$existingSyncTaskXml = if ($existingSyncTask) { Export-ScheduledTask -TaskPath $guardTaskPath -TaskName $syncTaskName } else { $null }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$manifest = @{}
foreach ($item in $files) {
    $target = Join-Path $item.Root $item.Relative
    $key = "$($item.Root)|$($item.Relative)"
    $backup = Join-Path $backupRoot (($key -replace '[:\\|]', '_') + '.bak')
    $existed = Test-Path -LiteralPath $target -PathType Leaf
    if ($existed) { Copy-Item -LiteralPath $target -Destination $backup -Force }
    $manifest[$key] = [pscustomobject]@{ existed = $existed; backup = $backup }
}

$taskPaused = $false
$serviceStopped = $false
$filesDeployed = $false
$rollbackApplied = $false
try {
    foreach ($item in $files | Where-Object { $_.Root -eq $standalone }) { Install-File $item }
    foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
        if ($value) { Set-Item -Path "Env:$name" -Value $value }
    }
    $env:IMES_OPS_DB_HOST = '10.10.181.195'
    $env:IMES_OPS_DB_PORT = '5432'
    $env:IMES_LAB_DB_HOST = '10.10.181.195'
    $env:IMES_LAB_DB_PORT = '5432'
    $env:PYTHONUTF8 = '1'
    Push-Location -LiteralPath $standalone
    try {
        & $python -X utf8 '.\tools\sync_22012_heat_performance_quality.py' --since-days 3 --max-heats 3 --dry-run
        if ($LASTEXITCODE -ne 0) { throw 'remote IMES aggregation dry-run failed' }
        & $python -X utf8 '.\tools\sync_22012_heat_performance_quality.py' --since-days 3
        if ($LASTEXITCODE -ne 0) { throw 'incremental heat-performance refresh failed' }
    } finally {
        Pop-Location
    }

    $runner = Join-Path $standalone 'tools\run_22012_heat_performance_sync.ps1'
    $action = New-ScheduledTaskAction -Execute $powershell -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskPath $guardTaskPath -TaskName $syncTaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    $taskPaused = $true
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Stopped'
    Wait-Port 8093 $false
    $serviceStopped = $true
    foreach ($port in @(8768, 8094, 8770)) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[$port]) { throw "protected port $port changed before deploy" }
    }
    foreach ($item in $files | Where-Object { $_.Root -eq $root }) { Install-File $item }
    $filesDeployed = $true
    & $python -m py_compile (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py') (Join-Path $root '高炉前端数据\智能助手\backend\heat_performance_quality.py')
    if ($LASTEXITCODE -ne 0) { throw 'deployed Python compile failed' }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    $serviceStopped = $false
    $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?t=heat-performance-$stamp" -TimeoutSec 30
    if ([int]$page.StatusCode -ne 200 -or $page.Content -notmatch 'bf-heat-performance-quality-8093.js') { throw '8093 page marker missing' }
    $api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/heat-performance-quality?limit=3&t=$stamp" -TimeoutSec 30
    if (-not $api.ok -or @($api.items).Count -lt 1) { throw '8093 heat-performance API returned no facts' }
    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    $filesDeployed = $true
} catch {
    $deployError = $_
    try {
        if ((Get-Service -Name $serviceName).Status.ToString() -ne 'Stopped') {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $configPath | Out-Null
            Wait-ServiceState $serviceName 'Stopped'
            Wait-Port 8093 $false
        }
        Restore-Files
        $rollbackApplied = $true
        if ($existingSyncTaskXml) {
            Register-ScheduledTask -TaskPath $guardTaskPath -TaskName $syncTaskName -Xml $existingSyncTaskXml -Force | Out-Null
        } else {
            Unregister-ScheduledTask -TaskPath $guardTaskPath -TaskName $syncTaskName -Confirm:$false -ErrorAction SilentlyContinue
        }
    } catch { Write-Warning "rollback failed: $($_.Exception.Message)" }
    Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue | Out-Null
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $configPath | Out-Null
    Wait-ServiceState $serviceName 'Running'
    Wait-Port 8093 $true
    throw $deployError
}

$listenersAfter = @{}
$listenersAfter[8093] = (Get-Listener 8093).pid
foreach ($port in @(8768, 8094, 8770)) { $listenersAfter[$port] = Get-ListenerPid $port }
foreach ($port in @(8768, 8094, 8770)) {
    if ($listenersAfter[$port] -ne $protectedBefore[$port]) { throw "protected PID changed on $port" }
}
$apiFinal = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?limit=3' -TimeoutSec 30
$deployedHashes = @{}
foreach ($item in $files) {
    $target = Join-Path $item.Root $item.Relative
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "deployed hash mismatch: $target" }
    $deployedHashes["$($item.Root)|$($item.Relative)"] = $actual
}

[ordered]@{
    schema = 'ops.8093.heat-performance-quality.v1'
    requirement_id = 'REQ-8093-HEAT-PERFORMANCE-QUALITY-20260806'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    service_state_before = $serviceStateBefore
    listener_8093_before = if ($listener8093Before) { $listener8093Before.pid } else { $null }
    listener_8093_after = $listenersAfter[8093]
    guard_paused = $taskPaused
    guard_restored = (Get-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath).State.ToString() -ne 'Disabled'
    sync_task_state = (Get-ScheduledTask -TaskName $syncTaskName -TaskPath $guardTaskPath).State.ToString()
    api_count = @($apiFinal.items).Count
    latest_meltno = @($apiFinal.items)[0].meltno
    latest_si_avg = @($apiFinal.items)[0].si_avg
    rollback_applied = $rollbackApplied
    protected_pids = [ordered]@{
        port_8768_before = $protectedBefore[8768]; port_8768_after = $listenersAfter[8768]
        port_8094_before = $protectedBefore[8094]; port_8094_after = $listenersAfter[8094]
        port_8770_before = $protectedBefore[8770]; port_8770_after = $listenersAfter[8770]
    }
    deployed_hashes = $deployedHashes
} | ConvertTo-Json -Depth 8
