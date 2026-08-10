$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

# This script is uploaded and executed on 220.12 by remote_22012_exec.py.
# It deliberately keeps database credentials in process memory only.
$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$frontendName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6auY54KJ5YmN56uv5pWw5o2u"))
$serviceName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6Ieq5Yqo6K+K5pat5pyN5Yqh"))
$engineName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6LCD5o6n57uT6K6655Sf5oiQ5byV5pOO"))
$temp = "C:\Users\Administrator\AppData\Local\Temp"
$archive = Join-Path $temp "recommendation_sync_20260806_r3.zip"
$payload = Join-Path $temp "recommendation_sync_20260806_r3"
$frontendDir = Join-Path $root $frontendName
$serviceDir = Join-Path $root $serviceName
$engineDir = Join-Path $root $engineName
$toolsDir = Join-Path $root "tools"
$page8093 = Join-Path $frontendDir "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontendDir "frontend_dashboard_v3.8094_preview.server.html"
$service8768 = "BFV4PreviewWs8768"
$guardService = "BFV4PreviewProxy8093"
$healthTaskPath = "\BlastFurnaceServices\"
$healthTaskName = "BFV4PreviewWs8768HealthCheck"
$python = "C:\Program Files\Python311\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\foreman_dual_control_20260806\$stamp"
$stage = Join-Path $root ".deploy_staging\foreman_dual_control_$stamp"
$restart8094 = Join-Path $toolsDir "restart_22012_8094_preview.ps1"
$manager = Join-Path $toolsDir "manage_22012_managed_services.ps1"
$guardConfig = Join-Path $toolsDir "service_configs\22012_BFV4PreviewProxy8093.json"
$serviceStopped = $false
$guardPaused = $false
$mutationStarted = $false
$healthTaskWasRunning = $false
$healthTaskWasEnabled = $false
$success = $false

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 150) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = $null -ne (Get-ListenerPid $Port)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Install-FileAtomic([string]$Source, [string]$Target) {
    $parent = Split-Path -Parent $Target
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $temporary = "$Target.foreman_dual_control.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Invoke-Http([string]$Uri) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 30 }
        catch {
            $lastError = $_
            if ($attempt -lt 10) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

function Get-EnvValue([string]$Name, [string]$Default = "") {
    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) { $value = [Environment]::GetEnvironmentVariable($Name, "Machine") }
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Invoke-Psql([string[]]$Arguments) {
    $psqlCommand = Get-Command "psql.exe" -ErrorAction SilentlyContinue
    $psql = if ($psqlCommand) { $psqlCommand.Source } else { "C:\Program Files\PostgreSQL\16\bin\psql.exe" }
    if (-not (Test-Path -LiteralPath $psql -PathType Leaf)) { throw "PostgreSQL client is missing: $psql" }
    & $psql @Arguments
    if ($LASTEXITCODE -ne 0) { throw "psql failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Deployment archive is missing: $archive" }
if (Test-Path -LiteralPath $payload) { throw "Temporary payload already exists: $payload" }
if ((Get-Service -Name $service8768 -ErrorAction Stop).Status -ne "Running") { throw "8768 service is not running" }
if (-not (Test-Path -LiteralPath $manager -PathType Leaf)) { throw "8093 managed-service guard script is missing" }
if (-not (Test-Path -LiteralPath $guardConfig -PathType Leaf)) { throw "8093 managed-service guard config is missing" }

$pidBefore = [ordered]@{
    P8093 = Get-ListenerPid 8093
    P8094 = Get-ListenerPid 8094
    P8768 = Get-ListenerPid 8768
    P8770 = Get-ListenerPid 8770
    P11434 = Get-ListenerPid 11434
}
foreach ($port in @(8093, 8094, 8768, 8770, 11434)) {
    if (-not $pidBefore["P$port"]) { throw "Required protected port is not listening: $port" }
}

Expand-Archive -LiteralPath $archive -DestinationPath $payload -Force
$manifestPath = Join-Path $payload "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Manifest is missing" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne "recommendation_sync_manifest.v2") { throw "Unexpected manifest schema" }
if ($manifest.operation -ne "REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806") { throw "Unexpected deployment operation" }
foreach ($property in $manifest.files.PSObject.Properties) {
    $path = Join-Path $payload ($property.Name.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Payload file missing: $($property.Name)" }
    if ((Get-Sha256 $path) -ne $property.Value.sha256) { throw "Payload hash mismatch: $($property.Name)" }
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$stageService = Join-Path $stage "runtime\$serviceName"
$stageEngine = Join-Path $stage "runtime\$engineName"
New-Item -ItemType Directory -Path $stageService -Force | Out-Null
New-Item -ItemType Directory -Path $stageEngine -Force | Out-Null
foreach ($property in $manifest.files.PSObject.Properties) {
    if ($property.Name.StartsWith("runtime/")) {
        $source = Join-Path $payload ($property.Name.Replace("/", "\"))
        $relative = $property.Name.Substring("runtime/".Length).Replace("/", "\")
        $targetStage = Join-Path $stage "runtime\$relative"
        $parent = Split-Path -Parent $targetStage
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $targetStage -Force
    }
}
$stage8093 = Join-Path $stage "frontend_dashboard_v3.server.html"
$stage8094 = Join-Path $stage "frontend_dashboard_v3.8094_preview.server.html"
Copy-Item -LiteralPath (Join-Path $payload "source\frontend_dashboard_v3.server.html") -Destination $stage8093 -Force
Copy-Item -LiteralPath $page8094 -Destination $stage8094 -Force
& $python -X utf8 (Join-Path $payload "tools\patch_8094_multi_condition_review.py") --target $stage8094 --feature-source $stage8093 --ws-port 8768
if ($LASTEXITCODE -ne 0) { throw "8094 page patch failed" }

$compileFiles = @(Get-ChildItem -LiteralPath (Join-Path $stage "runtime") -Recurse -Filter "*.py" -File | ForEach-Object { $_.FullName })
& $python -X utf8 -m py_compile @compileFiles
if ($LASTEXITCODE -ne 0) { throw "Python compile validation failed" }
& $python -X utf8 (Join-Path $payload "tools\verify_8094_multi_condition_package.py") --preview-root $stageService --engine-dir $stageEngine
if ($LASTEXITCODE -ne 0) { throw "Recommendation package contract validation failed" }

$adminUser = Get-EnvValue "GL02_PGADMIN_USER" "postgres"
$adminPassword = Get-EnvValue "GL02_PGADMIN_PASSWORD"
if ([string]::IsNullOrWhiteSpace($adminPassword)) { throw "GL02_PGADMIN_PASSWORD is missing" }
$env:PGPASSWORD = $adminPassword
$env:GL02_PGUSER = $adminUser
$env:GL02_PGPASSWORD = $adminPassword
$env:GL02_PGHOST = "127.0.0.1"
$env:GL02_PGPORT = "5432"
$env:GL02_PGDATABASE = "bf_trend"
try {
    & $python -X utf8 (Join-Path $payload "tools\migrate_foreman_pressure_quartiles.py") --host 127.0.0.1 --port 5432 --database bf_trend --user $adminUser
    if ($LASTEXITCODE -ne 0) { throw "Pressure quartile database migration failed" }
    & $python -X utf8 (Join-Path $payload "tools\migrate_recommendation_audit.py") --schema-path (Join-Path $stageService "recommendation_audit_schema.sql") --host 127.0.0.1 --port 5432 --database bf_trend --user $adminUser
    if ($LASTEXITCODE -ne 0) { throw "Recommendation audit database migration failed" }
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $baselineBuildOutput = & $python -X utf8 (Join-Path $stageService "baseline_maintainer.py") --build-day $today --baseline-days 30 --write --config (Join-Path $serviceDir "config.yaml")
    if ($LASTEXITCODE -ne 0) { throw "Real 30-day baseline Q1/Q3 backfill failed" }
    $baselineRaw = & $python -X utf8 (Join-Path $payload "tools\migrate_foreman_pressure_quartiles.py") --host 127.0.0.1 --port 5432 --database bf_trend --user $adminUser --require-variable P_blast_cold
    if ($LASTEXITCODE -ne 0) { throw "P_blast_cold baseline verification query failed" }
    $baselineResult = $baselineRaw | ConvertFrom-Json
    if (-not $baselineResult.ok -or -not $baselineResult.latest_baseline) { throw "No real P_blast_cold 30-day baseline with p25/p75 was written" }
    $baselineSnapshot = $baselineResult.latest_baseline
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:GL02_PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:GL02_PGUSER -ErrorAction SilentlyContinue
    Remove-Item Env:GL02_PGHOST -ErrorAction SilentlyContinue
    Remove-Item Env:GL02_PGPORT -ErrorAction SilentlyContinue
    Remove-Item Env:GL02_PGDATABASE -ErrorAction SilentlyContinue
}

$healthTask = Get-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName -ErrorAction SilentlyContinue
if ($healthTask) {
    $healthTaskWasRunning = $healthTask.State -eq "Running"
    $healthTaskWasEnabled = [bool]$healthTask.Settings.Enabled
    if ($healthTaskWasRunning) { Stop-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName }
    if ($healthTaskWasEnabled) { Disable-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName | Out-Null }
}

$runtimeBackupDir = Join-Path $backup "runtime"
$toolsBackupDir = Join-Path $backup "tools"
New-Item -ItemType Directory -Path $runtimeBackupDir -Force | Out-Null
New-Item -ItemType Directory -Path $toolsBackupDir -Force | Out-Null
$existed = @{}
$toolsExisted = @{}
foreach ($property in $manifest.files.PSObject.Properties) {
    if (-not $property.Name.StartsWith("runtime/")) { continue }
    $relative = $property.Name.Substring("runtime/".Length).Replace("/", "\")
    $target = Join-Path $root $relative
    $backupTarget = Join-Path $runtimeBackupDir $relative
    $existed[$property.Name] = Test-Path -LiteralPath $target -PathType Leaf
    if ($existed[$property.Name]) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $backupTarget) -Force | Out-Null
        Copy-Item -LiteralPath $target -Destination $backupTarget -Force
    }
}
foreach ($property in $manifest.files.PSObject.Properties) {
    if (-not $property.Name.StartsWith("tools/")) { continue }
    $relative = $property.Name.Substring("tools/".Length).Replace("/", [char]92)
    $target = Join-Path $toolsDir $relative
    $backupTarget = Join-Path $toolsBackupDir $relative
    $toolsExisted[$property.Name] = Test-Path -LiteralPath $target -PathType Leaf
    if ($toolsExisted[$property.Name]) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $backupTarget) -Force | Out-Null
        Copy-Item -LiteralPath $target -Destination $backupTarget -Force
    }
}
$page8093Backup = Join-Path $backup "frontend_dashboard_v3.server.html"
$page8094Backup = Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html"
$restartBackup = Join-Path $backup "restart_22012_8094_preview.ps1"
Copy-Item -LiteralPath $page8093 -Destination $page8093Backup -Force
Copy-Item -LiteralPath $page8094 -Destination $page8094Backup -Force
if (Test-Path -LiteralPath $restart8094 -PathType Leaf) { Copy-Item -LiteralPath $restart8094 -Destination $restartBackup -Force }
Copy-Item -LiteralPath $engineDir -Destination (Join-Path $backup $engineName) -Recurse -Force

try {
    Stop-Service -Name $service8768 -Force
    $serviceStopped = $true
    Wait-Port 8768 $false 90
    $mutationStarted = $true

    if (Test-Path -LiteralPath $engineDir) { Remove-Item -LiteralPath $engineDir -Recurse -Force }
    Move-Item -LiteralPath $stageEngine -Destination $engineDir
    foreach ($property in $manifest.files.PSObject.Properties) {
        if (-not $property.Name.StartsWith("runtime/") -or $property.Name.StartsWith("runtime/$engineName/")) { continue }
        $relative = $property.Name.Substring("runtime/".Length).Replace("/", "\")
        Install-FileAtomic (Join-Path $stage "runtime\$relative") (Join-Path $root $relative)
    }
    Install-FileAtomic $stage8094 $page8094
    foreach ($property in $manifest.files.PSObject.Properties) {
        if (-not $property.Name.StartsWith("tools/")) { continue }
        $relative = $property.Name.Substring("tools/".Length).Replace("/", [char]92)
        Install-FileAtomic (Join-Path $payload ($property.Name.Replace("/", [char]92))) (Join-Path $toolsDir $relative)
    }

    foreach ($property in $manifest.files.PSObject.Properties) {
        if ($property.Name.StartsWith("runtime/")) {
            $remoteTarget = Join-Path $root ($property.Name.Substring("runtime/".Length).Replace("/", "\"))
        } elseif ($property.Name.StartsWith("tools/")) {
            $remoteTarget = Join-Path $root ($property.Name.Replace("/", "\"))
        } else { continue }
        if (-not (Test-Path -LiteralPath $remoteTarget -PathType Leaf) -or (Get-Sha256 $remoteTarget) -ne $property.Value.sha256) {
            throw "Installed hash mismatch: $($property.Name)"
        }
    }

    Start-Service -Name $service8768
    $serviceStopped = $false
    Wait-Port 8768 $true 150
    if ($healthTask -and $healthTaskWasEnabled) { Enable-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName | Out-Null }
    & $python -X utf8 (Join-Path $payload "tools\verify_foreman_dual_control_runtime.py") --uri "ws://127.0.0.1:8768" --timeout 120
    if ($LASTEXITCODE -ne 0) { throw "8768 foreman dual-control runtime validation failed" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    if ($LASTEXITCODE -ne 0) { throw "8094 controlled restart failed" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $guardConfig
    $guardPaused = $true
    Wait-Port 8093 $false 90
    Install-FileAtomic $stage8093 $page8093
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig
    Wait-Port 8093 $true 150
    $guardPaused = $false

    $http8093 = Invoke-Http "http://127.0.0.1:8093/?foreman_dual_control=$stamp#optimization"
    $http8094 = Invoke-Http "http://127.0.0.1:8094/?foreman_dual_control=$stamp#optimization"
    foreach ($response in @($http8093, $http8094)) {
        if ($response.StatusCode -ne 200) { throw "Recommendation page HTTP status is not 200" }
        if (-not $response.Content.Contains("REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806")) { throw "visual cockpit marker is missing" }
        if (-not $response.Content.Contains("foreman-dual-control-unavailable")) { throw "dual-control fallback guard marker is missing" }
        if ($response.Content.Contains("control_variable: 'Q_blast'") -or $response.Content.Contains('control_variable: "Q_blast"')) { throw "old Q_blast executable action remains in page" }
    }
    if ((Get-ListenerPid 8770) -ne $pidBefore.P8770) { throw "8770 process changed unexpectedly" }
    if ((Get-ListenerPid 11434) -ne $pidBefore.P11434) { throw "11434 process changed unexpectedly" }
    if ((Get-ListenerPid 8768) -eq $pidBefore.P8768) { throw "8768 was not restarted" }
    if (-not (Get-ListenerPid 8093) -or -not (Get-ListenerPid 8094)) { throw "8093/8094 are not listening after deployment" }

    $success = $true
    [ordered]@{
        ok = $true
        operation = $manifest.operation
        deployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        backup = $backup
        engineVersion = $manifest.engine_version
        manifestFileCount = @($manifest.files.PSObject.Properties).Count
        baseline = $baselineSnapshot
        pid8768Before = $pidBefore.P8768
        pid8768After = Get-ListenerPid 8768
        pid8093After = Get-ListenerPid 8093
        pid8094After = Get-ListenerPid 8094
        pid8770Unchanged = ((Get-ListenerPid 8770) -eq $pidBefore.P8770)
        pid11434Unchanged = ((Get-ListenerPid 11434) -eq $pidBefore.P11434)
        http8093 = [int]$http8093.StatusCode
        http8094 = [int]$http8094.StatusCode
        page8093Sha256 = Get-Sha256 $page8093
        page8094Sha256 = Get-Sha256 $page8094
        enginePolicySha256 = Get-Sha256 (Join-Path $engineDir "policy\three_rules_two_systems.yaml")
        adapterSha256 = Get-Sha256 (Join-Path $serviceDir "recommendation_adapter.py")
        bridgeSha256 = Get-Sha256 (Join-Path $serviceDir "local_pg_ws_bridge.py")
        guardPaused = $true
        guardRestored = $true
        readOnly = $true
    } | ConvertTo-Json -Depth 8
}
catch {
    $failure = $_
    if ($guardPaused) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig -ErrorAction SilentlyContinue
        Wait-Port 8093 $true 120
    }
    if ($mutationStarted) {
        if ((Get-Service -Name $service8768 -ErrorAction SilentlyContinue).Status -eq "Running") {
            Stop-Service -Name $service8768 -Force -ErrorAction SilentlyContinue
            Wait-Port 8768 $false 60
        }
        if (Test-Path -LiteralPath $engineDir) { Remove-Item -LiteralPath $engineDir -Recurse -Force -ErrorAction SilentlyContinue }
        Copy-Item -LiteralPath (Join-Path $backup $engineName) -Destination $engineDir -Recurse -Force
        foreach ($property in $manifest.files.PSObject.Properties) {
            if (-not $property.Name.StartsWith("runtime/")) { continue }
            $relative = $property.Name.Substring("runtime/".Length).Replace("/", "\")
            $backupTarget = Join-Path $runtimeBackupDir $relative
            $target = Join-Path $root $relative
            if ($existed[$property.Name]) { Install-FileAtomic $backupTarget $target }
            else { Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue }
        }
        foreach ($property in $manifest.files.PSObject.Properties) {
            if (-not $property.Name.StartsWith("tools/")) { continue }
            $relative = $property.Name.Substring("tools/".Length).Replace("/", [char]92)
            $backupTarget = Join-Path $toolsBackupDir $relative
            $target = Join-Path $toolsDir $relative
            if ($toolsExisted[$property.Name]) { Install-FileAtomic $backupTarget $target }
            else { Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue }
        }
        Install-FileAtomic $page8093Backup $page8093
        Install-FileAtomic $page8094Backup $page8094
        if (Test-Path -LiteralPath $restartBackup -PathType Leaf) { Install-FileAtomic $restartBackup $restart8094 }
        Start-Service -Name $service8768 -ErrorAction SilentlyContinue
        Wait-Port 8768 $true 150
    }
    if ($healthTask -and $healthTaskWasEnabled) { Enable-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName -ErrorAction SilentlyContinue | Out-Null }
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
    if (-not $success) { Write-Warning "Foreman dual-control deployment failed; rollback was attempted from $backup" }
}
