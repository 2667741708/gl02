$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$serviceName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6Ieq5Yqo6K+K5pat5pyN5Yqh"))
$engineName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6LCD5o6n57uT6K6655Sf5oiQ5byV5pOO"))
$temp = "C:\Users\Administrator\AppData\Local\Temp"
$archive = Join-Path $temp "recommendation_audit_deploy.zip"
$payload = Join-Path $temp "recommendation_audit_deploy_payload"
$serviceDir = Join-Path $root $serviceName
$toolsDir = Join-Path $root "tools"
$engineDir = Join-Path $root $engineName
$service8768 = "BFV4PreviewWs8768"
$healthTaskPath = "\BlastFurnaceServices\"
$healthTaskName = "BFV4PreviewWs8768HealthCheck"
$python = "C:\Program Files\Python311\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\recommendation_audit_20260806\$stamp"
$stage = Join-Path $root ".deploy_staging\recommendation_audit_$stamp"
$serviceStopped = $false
$mutationStarted = $false
$success = $false
$healthTaskWasEnabled = $false
$healthTaskPaused = $false

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = $null -ne (Get-ListenerPid $Port)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Start-ServiceWithRetry([string]$Name, [int]$Attempts = 12) {
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Start-Service -Name $Name -ErrorAction Stop
        }
        catch {
            $lastError = $_
        }
        if ((Get-Service -Name $Name -ErrorAction SilentlyContinue).Status -eq "Running") {
            return
        }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds 5 }
    }
    if ($lastError) { throw $lastError }
    throw "Service did not enter Running state: $Name"
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Install-FileAtomic([string]$Source, [string]$Target) {
    $temporary = "$Target.recommendation_audit.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

function Invoke-Http([string]$Uri) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 30 }
        catch {
            $lastError = $_
            if ($attempt -lt 8) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Deployment archive is missing" }
if (Test-Path -LiteralPath $payload) { throw "Temporary payload already exists: $payload" }
if ((Get-Service -Name $service8768 -ErrorAction Stop).Status -ne "Running") { throw "8768 service is not running" }
$healthTask = Get-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName -ErrorAction Stop
$healthTaskWasEnabled = [bool]$healthTask.Settings.Enabled
foreach ($port in @(8768, 8770)) {
    if (-not (Get-ListenerPid $port)) { throw "Required port is not listening: $port" }
}

$pid8093Before = Get-ListenerPid 8093
$pid8094Before = Get-ListenerPid 8094
$pid8768Before = Get-ListenerPid 8768
$pid8770Before = Get-ListenerPid 8770
$page8093Before = if ($pid8093Before) { (Invoke-Http "http://127.0.0.1:8093/?audit_precheck=$stamp").StatusCode } else { $null }
$page8094Before = if ($pid8094Before) { (Invoke-Http "http://127.0.0.1:8094/?audit_precheck=$stamp").StatusCode } else { $null }

Expand-Archive -LiteralPath $archive -DestinationPath $payload -Force
$manifestPath = Join-Path $payload "manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Manifest is missing" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema_version -ne "recommendation_audit_deploy_manifest.v1") { throw "Unexpected manifest schema" }
if ($manifest.operation -ne "REQ-RECOMMENDATION-FULL-AUDIT-20260806") { throw "Unexpected deployment operation" }
foreach ($property in $manifest.files.PSObject.Properties) {
    $path = Join-Path $payload ($property.Name.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Payload file missing: $($property.Name)" }
    if ((Get-Sha256 $path) -ne $property.Value.sha256) { throw "Payload hash mismatch: $($property.Name)" }
}
$remotePolicy = Join-Path $engineDir "policy\three_rules_two_systems.yaml"
if ((Get-Sha256 $remotePolicy) -ne $manifest.policy_sha256) { throw "Remote policy hash differs from the audited local policy" }

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$targets = [ordered]@{
    "recommendation_adapter.py" = Join-Path $serviceDir "recommendation_adapter.py"
    "local_pg_ws_bridge.py" = Join-Path $serviceDir "local_pg_ws_bridge.py"
    "recommendation_audit_store.py" = Join-Path $serviceDir "recommendation_audit_store.py"
    "recommendation_audit_schema.sql" = Join-Path $serviceDir "recommendation_audit_schema.sql"
    "migrate_recommendation_audit.py" = Join-Path $toolsDir "migrate_recommendation_audit.py"
    "verify_recommendation_audit_runtime.py" = Join-Path $toolsDir "verify_recommendation_audit_runtime.py"
}
$existed = @{}
foreach ($entry in $targets.GetEnumerator()) {
    $existed[$entry.Key] = Test-Path -LiteralPath $entry.Value -PathType Leaf
    if ($existed[$entry.Key]) { Copy-Item -LiteralPath $entry.Value -Destination (Join-Path $backup $entry.Key) -Force }
}

try {
    $stageService = Join-Path $stage $serviceName
    $stageTools = Join-Path $stage "tools"
    New-Item -ItemType Directory -Path $stageService -Force | Out-Null
    New-Item -ItemType Directory -Path $stageTools -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $payload "runtime\$serviceName\recommendation_adapter.py") -Destination $stageService -Force
    Copy-Item -LiteralPath (Join-Path $payload "runtime\$serviceName\local_pg_ws_bridge.py") -Destination $stageService -Force
    Copy-Item -LiteralPath (Join-Path $payload "runtime\$serviceName\recommendation_audit_store.py") -Destination $stageService -Force
    Copy-Item -LiteralPath (Join-Path $payload "runtime\$serviceName\recommendation_audit_schema.sql") -Destination $stageService -Force
    Copy-Item -LiteralPath (Join-Path $payload "tools\migrate_recommendation_audit.py") -Destination $stageTools -Force
    Copy-Item -LiteralPath (Join-Path $payload "tools\verify_recommendation_audit_runtime.py") -Destination $stageTools -Force

    $compileFiles = @(
        (Join-Path $stageService "recommendation_adapter.py"),
        (Join-Path $stageService "local_pg_ws_bridge.py"),
        (Join-Path $stageService "recommendation_audit_store.py"),
        (Join-Path $stageTools "migrate_recommendation_audit.py"),
        (Join-Path $stageTools "verify_recommendation_audit_runtime.py")
    )
    & $python -X utf8 -m py_compile @compileFiles
    if ($LASTEXITCODE -ne 0) { throw "Python compile validation failed" }

    $adminPassword = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_PASSWORD", "Machine")
    if ([string]::IsNullOrWhiteSpace($adminPassword)) { throw "Machine GL02_PGADMIN_PASSWORD is missing" }
    $env:GL02_PGADMIN_PASSWORD = $adminPassword
    & $python -X utf8 (Join-Path $stageTools "migrate_recommendation_audit.py") --schema-path (Join-Path $stageService "recommendation_audit_schema.sql") --host 127.0.0.1 --port 5432 --database bf_trend --user postgres
    if ($LASTEXITCODE -ne 0) { throw "Recommendation audit database migration failed" }

    if ($healthTask.State -eq "Running") {
        Stop-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName
    }
    if ($healthTaskWasEnabled) {
        Disable-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName | Out-Null
    }
    $healthTaskPaused = $true

    Stop-Service -Name $service8768 -Force
    $serviceStopped = $true
    Wait-Port 8768 $false 90
    $mutationStarted = $true

    foreach ($entry in $targets.GetEnumerator()) {
        $source = if ($entry.Key -in @("migrate_recommendation_audit.py", "verify_recommendation_audit_runtime.py")) {
            Join-Path $stageTools $entry.Key
        } else {
            Join-Path $stageService $entry.Key
        }
        Install-FileAtomic $source $entry.Value
    }
    foreach ($property in $manifest.files.PSObject.Properties) {
        $relative = $property.Name
        $target = if ($relative.StartsWith("runtime/$serviceName/")) {
            Join-Path $serviceDir ($relative.Substring(("runtime/$serviceName/").Length))
        } elseif ($relative.StartsWith("tools/")) {
            Join-Path $toolsDir ($relative.Substring("tools/".Length))
        } else { $null }
        if ($target -and (Get-Sha256 $target) -ne $property.Value.sha256) {
            throw "Pre-start installed hash mismatch: $relative"
        }
    }

    Start-ServiceWithRetry $service8768 12
    $serviceStopped = $false
    Wait-Port 8768 $true 150

    & $python -X utf8 (Join-Path $stageTools "verify_recommendation_audit_runtime.py") --uri "ws://127.0.0.1:8768" --timeout 120 --host 127.0.0.1 --port 5432 --database bf_trend --user postgres
    if ($LASTEXITCODE -ne 0) { throw "Recommendation audit runtime acceptance failed" }

    $http8093 = if ($pid8093Before) { Invoke-Http "http://127.0.0.1:8093/?recommendation_audit=$stamp#optimization" } else { $null }
    $http8094 = if ($pid8094Before) { Invoke-Http "http://127.0.0.1:8094/?recommendation_audit=$stamp#optimization" } else { $null }
    if ($http8093 -and $http8093.StatusCode -ne 200) { throw "8093 HTTP verification failed" }
    if ($http8094 -and $http8094.StatusCode -ne 200) { throw "8094 HTTP verification failed" }
    if ($pid8093Before -and (Get-ListenerPid 8093) -ne $pid8093Before) { throw "8093 process changed unexpectedly" }
    if ($pid8094Before -and (Get-ListenerPid 8094) -ne $pid8094Before) { throw "8094 process changed unexpectedly" }
    if ((Get-ListenerPid 8770) -ne $pid8770Before) { throw "8770 process changed unexpectedly" }
    foreach ($property in $manifest.files.PSObject.Properties) {
        $relative = $property.Name
        $target = if ($relative.StartsWith("runtime/$serviceName/")) {
            Join-Path $serviceDir ($relative.Substring(("runtime/$serviceName/").Length))
        } elseif ($relative.StartsWith("tools/")) {
            Join-Path $toolsDir ($relative.Substring("tools/".Length))
        } else { $null }
        if ($target -and (Get-Sha256 $target) -ne $property.Value.sha256) { throw "Installed hash mismatch: $relative" }
    }

    $success = $true
    [ordered]@{
        ok = $true
        operation = $manifest.operation
        deployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        backup = $backup
        auditSchemaVersion = "recommendation_audit.v1"
        engineVersion = $manifest.engine_version
        policySha256 = $manifest.policy_sha256
        pid8768Before = $pid8768Before
        pid8768After = Get-ListenerPid 8768
        pid8093Unchanged = if ($pid8093Before) { (Get-ListenerPid 8093) -eq $pid8093Before } else { $null }
        pid8094Unchanged = if ($pid8094Before) { (Get-ListenerPid 8094) -eq $pid8094Before } else { $null }
        pid8770Unchanged = ((Get-ListenerPid 8770) -eq $pid8770Before)
        http8093Before = $page8093Before
        http8093After = if ($http8093) { [int]$http8093.StatusCode } else { $null }
        http8094Before = $page8094Before
        http8094After = if ($http8094) { [int]$http8094.StatusCode } else { $null }
        auditStoreSha256 = Get-Sha256 (Join-Path $serviceDir "recommendation_audit_store.py")
        auditSchemaSha256 = Get-Sha256 (Join-Path $serviceDir "recommendation_audit_schema.sql")
        adapterSha256 = Get-Sha256 (Join-Path $serviceDir "recommendation_adapter.py")
        bridgeSha256 = Get-Sha256 (Join-Path $serviceDir "local_pg_ws_bridge.py")
        healthTaskPaused = $healthTaskPaused
        healthTaskRestored = $healthTaskWasEnabled
    } | ConvertTo-Json -Depth 6
}
catch {
    $failure = $_
    if ($mutationStarted) {
        Stop-Service -Name $service8768 -Force -ErrorAction SilentlyContinue
        Wait-Port 8768 $false 60
        foreach ($entry in $targets.GetEnumerator()) {
            if ($existed[$entry.Key]) {
                Install-FileAtomic (Join-Path $backup $entry.Key) $entry.Value
            } else {
                Remove-Item -LiteralPath $entry.Value -Force -ErrorAction SilentlyContinue
            }
        }
    }
    if ((Get-Service -Name $service8768 -ErrorAction SilentlyContinue).Status -ne "Running") {
        try {
            Start-ServiceWithRetry $service8768 12
            Wait-Port 8768 $true 180
        }
        catch {
            Write-Warning "Rollback restored files but direct 8768 restart still needs the health task"
        }
    }
    throw $failure
}
finally {
    Remove-Item Env:GL02_PGADMIN_PASSWORD -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
    if ($healthTaskPaused -and $healthTaskWasEnabled) {
        Enable-ScheduledTask -TaskPath $healthTaskPath -TaskName $healthTaskName -ErrorAction SilentlyContinue | Out-Null
    }
    if (-not $success) { Write-Warning "Recommendation audit deployment failed; code rollback was attempted from $backup" }
}
