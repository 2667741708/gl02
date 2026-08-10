$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$backend = Join-Path $frontend "智能助手\backend"
$payload = "C:\Users\Administrator\AppData\Local\Temp\bf8094multi_r12"
$payloadArchive = "C:\Users\Administrator\AppData\Local\Temp\bf8094multi.zip"
$targetHtml = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$runner8094 = Join-Path $root "tools\run_22012_8094_preview.ps1"
$restart8094 = Join-Path $root "tools\restart_22012_8094_preview.ps1"
$sharedProxy = Join-Path $backend "ollama_proxy_server.py"
$isolatedProxy = Join-Path $backend "ollama_proxy_server_8094.py"
$modelReview = Join-Path $backend "diagnosis_model_review_8094.py"
$previewRoot = Join-Path $root "preview_8094_ws8769"
$previewEngine = Join-Path $previewRoot "recommendation_engine"
$wsRunner = Join-Path $root "tools\run_22012_8094_ws8769.ps1"
$wsLauncher = Join-Path $root "tools\run_22012_8094_ws8769.py"
$runtimeVerifier = Join-Path $root "tools\verify_8094_multi_condition_runtime.py"
$taskPath = "\BlastFurnaceServices\"
$task8094 = "V3AutoPreviewProxy8094"
$task8769 = "V4PreviewWs8769"
$firewallName = "BlastFurnaceV4PreviewWs8769"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\8094_multi_condition_review_20260805\$stamp"
$stage = Join-Path $root ".deploy_staging\8094_multi_condition_review_$stamp"
$html8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$html8094BaselineSha256 = "A13AB868BA7D71FC04450D05BD88D23506DB6BB7103C1165D5CCFD2021D193C7"
$runner8094BaselineSha256 = "5B0851CA689236CEC73271EC3A822C85AC9123ECE13C7F7183926C1425E55D94"
$sharedProxySha256 = "B53F01E063138A623B091CB3F36DD72971FF5B844FB2D27C06C222BB417FF5F6"
$html8093BaselineSha256 = "356BB43BCC2DD45A28B208C3D5B24F91654851CAE10DDCF0B89861CC4B591DF1"
$deploymentSucceeded = $false
$task8769Created = $false
$firewallCreated = $false
$runtimeChanged = $false
$restart8094Existed = Test-Path -LiteralPath $restart8094 -PathType Leaf

function Get-ListenerPid {
    param([Parameter(Mandatory = $true)][int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $listener) { return $null }
    return [int]$listener.OwningProcess
}

function Wait-Port {
    param([Parameter(Mandatory = $true)][int]$Port, [Parameter(Mandatory = $true)][bool]$Listening, [int]$TimeoutSeconds = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = $null -ne (Get-ListenerPid -Port $Port)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Write-Utf8NoBom {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Text)
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Invoke-HttpWithRetry {
    param([Parameter(Mandatory = $true)][string]$Uri, [int]$Attempts = 6)
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 30 }
        catch {
            $lastError = $_
            if ($attempt -lt $Attempts) { Start-Sleep -Seconds 2 }
        }
    }
    throw $lastError
}

if (Test-Path -LiteralPath $payload) {
    Remove-Item -LiteralPath $payload -Recurse -Force
}
if (-not (Test-Path -LiteralPath $payloadArchive -PathType Leaf)) { throw "Payload archive missing: $payloadArchive" }
Expand-Archive -LiteralPath $payloadArchive -DestinationPath $payload -Force

foreach ($source in @(
    "$payload\frontend_source.html",
    "$payload\patch_8094_multi_condition_review.py",
    "$payload\verify_8094_multi_condition_package.py",
    "$payload\verify_8094_multi_condition_runtime.py",
    "$payload\ollama_proxy_server_8094.py",
    "$payload\diagnosis_model_review_8094.py",
    "$payload\restart_22012_8094_preview.ps1",
    "$payload\run_22012_8094_preview.ps1",
    "$payload\run_22012_8094_ws8769.ps1",
    "$payload\run_22012_8094_ws8769.py",
    "$payload\preview_8094_ws8769\local_pg_ws_bridge.py",
    "$payload\preview_8094_ws8769\recommendation_adapter.py",
    "$payload\preview_8094_ws8769\recommendation_engine\policy\three_rules_two_systems.yaml",
    "$payload\preview_8094_ws8769\recommendation_engine\recommendation\core.py"
)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Payload file missing: $source" }
}

$pid8093Before = Get-ListenerPid -Port 8093
$pid8094Before = Get-ListenerPid -Port 8094
$pid8768Before = Get-ListenerPid -Port 8768
$pid8769Before = Get-ListenerPid -Port 8769
$pid8770Before = Get-ListenerPid -Port 8770
$pid11434Before = Get-ListenerPid -Port 11434
if (-not $pid8094Before -or -not $pid8768Before -or -not $pid8770Before -or -not $pid11434Before) {
    throw "Required services 8094/8768/8770/11434 must be healthy before deployment"
}
if ($pid8769Before) { throw "Port 8769 is already in use by PID $pid8769Before" }
if (Get-ScheduledTask -TaskPath $taskPath -TaskName $task8769 -ErrorAction SilentlyContinue) {
    throw "Preview task $task8769 already exists; refusing an ambiguous deployment"
}
if ((Get-ScheduledTask -TaskPath $taskPath -TaskName $task8094 -ErrorAction Stop).State -ne "Running") {
    throw "8094 preview task is not running"
}
if ((Get-Sha256 -Path $targetHtml) -ne $html8094BaselineSha256) { throw "8094 HTML baseline hash changed" }
if ((Get-Sha256 -Path $runner8094) -ne $runner8094BaselineSha256) { throw "8094 runner baseline hash changed" }
if (Test-Path -LiteralPath $isolatedProxy) { throw "Isolated 8094 proxy already exists" }
if (Test-Path -LiteralPath $modelReview) { throw "Diagnosis model review module already exists" }
if (Test-Path -LiteralPath $previewRoot) { throw "Isolated 8769 preview directory already exists" }

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force
Copy-Item -LiteralPath $runner8094 -Destination (Join-Path $backup "run_22012_8094_preview.ps1") -Force
if ($restart8094Existed) {
    Copy-Item -LiteralPath $restart8094 -Destination (Join-Path $backup "restart_22012_8094_preview.ps1") -Force
}

try {
    $stagedHtml = Join-Path $stage "frontend_dashboard_v3.8094_preview.server.html"
    Copy-Item -LiteralPath $targetHtml -Destination $stagedHtml -Force
    & "C:\Program Files\Python311\python.exe" -X utf8 "$payload\patch_8094_multi_condition_review.py" `
        --target $stagedHtml --feature-source "$payload\frontend_source.html"
    if ($LASTEXITCODE -ne 0) { throw "8094 HTML patcher failed" }

    $stagedPreview = Join-Path $stage "preview_8094_ws8769"
    Copy-Item -LiteralPath "$payload\preview_8094_ws8769" -Destination $stagedPreview -Recurse -Force
    foreach ($pythonFile in @(
        (Join-Path $stagedPreview "local_pg_ws_bridge.py"),
        (Join-Path $stagedPreview "recommendation_adapter.py"),
        "$payload\run_22012_8094_ws8769.py",
        "$payload\ollama_proxy_server_8094.py",
        "$payload\diagnosis_model_review_8094.py"
    )) {
        & "C:\Program Files\Python311\python.exe" -X utf8 -m py_compile $pythonFile
        if ($LASTEXITCODE -ne 0) { throw "Python compile failed: $pythonFile" }
    }
    & "C:\Program Files\Python311\python.exe" -X utf8 "$payload\verify_8094_multi_condition_package.py" `
        --preview-root $stagedPreview --engine-dir (Join-Path $stagedPreview "recommendation_engine")
    if ($LASTEXITCODE -ne 0) { throw "Isolated recommendation package verification failed" }

    Copy-Item -LiteralPath $stagedPreview -Destination $previewRoot -Recurse -Force
    Copy-Item -LiteralPath "$payload\ollama_proxy_server_8094.py" -Destination $isolatedProxy -Force
    Copy-Item -LiteralPath "$payload\diagnosis_model_review_8094.py" -Destination $modelReview -Force
    Copy-Item -LiteralPath "$payload\run_22012_8094_ws8769.ps1" -Destination $wsRunner -Force
    Copy-Item -LiteralPath "$payload\run_22012_8094_ws8769.py" -Destination $wsLauncher -Force
    Copy-Item -LiteralPath "$payload\verify_8094_multi_condition_runtime.py" -Destination $runtimeVerifier -Force
    Copy-Item -LiteralPath "$payload\restart_22012_8094_preview.ps1" -Destination $restart8094 -Force

    $stagedRunner = Join-Path $stage "run_22012_8094_preview.ps1"
    Copy-Item -LiteralPath "$payload\run_22012_8094_preview.ps1" -Destination $stagedRunner -Force
    Copy-Item -LiteralPath $stagedRunner -Destination $runner8094 -Force

    if (-not (Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $firewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8769 -Profile Any | Out-Null
        $firewallCreated = $true
    }

    Copy-Item -LiteralPath $stagedHtml -Destination $targetHtml -Force
    $runtimeChanged = $true
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    if ($LASTEXITCODE -ne 0) { throw "8094 isolated restart failed" }
    Wait-Port -Port 8769 -Listening $true -TimeoutSeconds 120
    & "C:\Program Files\Python311\python.exe" -X utf8 $runtimeVerifier --uri "ws://127.0.0.1:8769" --timeout 90
    if ($LASTEXITCODE -ne 0) { throw "8769 runtime bundle verification failed" }

    $served8094 = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/?multi_condition_deploy=$stamp#optimization"
    $servedText = [string]$served8094.Content
    if (
        $served8094.StatusCode -ne 200 -or
        -not $servedText.Contains("OPS-8094-MULTI-CONDITION-REVIEW-20260805") -or
        -not $servedText.Contains("get('ws_port') || '8769'")
    ) { throw "8094 HTTP contract verification failed" }

    $routeStatus = $null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/api/diagnosis/model-review" `
            -Method Post -ContentType "application/json" -Body "{}" -TimeoutSec 30 | Out-Null
        $routeStatus = 200
    } catch {
        if ($_.Exception.Response) { $routeStatus = [int]$_.Exception.Response.StatusCode }
    }
    if ($routeStatus -ne 400) { throw "Model review route validation expected HTTP 400, got $routeStatus" }

    $pid8093After = Get-ListenerPid -Port 8093
    $pid8094After = Get-ListenerPid -Port 8094
    $pid8768After = Get-ListenerPid -Port 8768
    $pid8769After = Get-ListenerPid -Port 8769
    $pid8770After = Get-ListenerPid -Port 8770
    $pid11434After = Get-ListenerPid -Port 11434
    if (
        $pid8768After -ne $pid8768Before -or
        $pid8770After -ne $pid8770Before -or $pid11434After -ne $pid11434Before
    ) { throw "A protected non-8093 service PID changed during 8094 deployment" }
    if (-not $pid8094After -or $pid8094After -eq $pid8094Before -or -not $pid8769After) {
        throw "8094 or isolated 8769 process state is invalid after deployment"
    }

    $deploymentSucceeded = $true
    [ordered]@{
        ok = $true
        deployedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        scope = "8094 isolated preview"
        backup = $backup
        html8094Sha256 = Get-Sha256 -Path $targetHtml
        isolatedProxySha256 = Get-Sha256 -Path $isolatedProxy
        modelReviewSha256 = Get-Sha256 -Path $modelReview
        sharedProxySha256 = Get-Sha256 -Path $sharedProxy
        html8093Sha256 = Get-Sha256 -Path $html8093
        pid8093ObservedBefore = $pid8093Before
        pid8093ObservedAfter = $pid8093After
        pid8768Unchanged = ($pid8768After -eq $pid8768Before)
        pid8770Unchanged = ($pid8770After -eq $pid8770Before)
        pid11434Unchanged = ($pid11434After -eq $pid11434Before)
        pid8094Before = $pid8094Before
        pid8094After = $pid8094After
        pid8769 = $pid8769After
        http8094 = [int]$served8094.StatusCode
        modelReviewRouteStatus = $routeStatus
        defaultWsPort = 8769
        conditionCount = 8
        restartScriptInstalled = $true
        readOnly = $true
    } | ConvertTo-Json -Depth 6
}
catch {
    $failure = $_
    Write-Warning ("8094 deployment failure: " + ($failure | Out-String))
    $failureLog = Join-Path $root "logs\8094_multi_condition_deploy_failure_latest.txt"
    [IO.File]::WriteAllText($failureLog, ($failure | Out-String), [Text.UTF8Encoding]::new($false))
    if ($task8769Created) {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $task8769 -ErrorAction SilentlyContinue
        $listener8769 = Get-ListenerPid -Port 8769
        if ($listener8769) { Stop-Process -Id $listener8769 -Force -ErrorAction SilentlyContinue }
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $task8769 -Confirm:$false -ErrorAction SilentlyContinue
    }
    if ($firewallCreated) { Remove-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue }
    $rollback8769 = Get-ListenerPid -Port 8769
    if ($rollback8769) {
        $rollback8769Process = Get-CimInstance Win32_Process -Filter "ProcessId=$rollback8769" -ErrorAction SilentlyContinue
        if ($rollback8769Process -and $rollback8769Process.CommandLine.Contains($wsLauncher)) {
            Stop-Process -Id $rollback8769 -Force -ErrorAction SilentlyContinue
            Wait-Port -Port 8769 -Listening $false -TimeoutSeconds 30
        }
    }
    Copy-Item -LiteralPath (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Destination $targetHtml -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath (Join-Path $backup "run_22012_8094_preview.ps1") -Destination $runner8094 -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $isolatedProxy -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $modelReview -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $previewRoot -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $wsRunner -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $wsLauncher -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $runtimeVerifier -Force -ErrorAction SilentlyContinue
    if ($runtimeChanged) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    }
    if ($restart8094Existed) {
        Copy-Item -LiteralPath (Join-Path $backup "restart_22012_8094_preview.ps1") -Destination $restart8094 -Force -ErrorAction SilentlyContinue
    } else {
        Remove-Item -LiteralPath $restart8094 -Force -ErrorAction SilentlyContinue
    }
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $payloadArchive) { Remove-Item -LiteralPath $payloadArchive -Force -ErrorAction SilentlyContinue }
    if (-not $deploymentSucceeded) { Write-Warning "8094 multi-condition deployment failed and rollback was attempted from $backup" }
}
