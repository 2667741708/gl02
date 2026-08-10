$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required'
}

$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$legacyCommandPart = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$expectedCommandPart = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server_8094.py"
$wsLauncherCommandPart = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\run_22012_8094_ws8769.py"
$frontendHtml = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$revisionMarker = "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"
$multiConditionMarker = "OPS-8094-MULTI-CONDITION-REVIEW-20260805"
$frontendContent = Get-Content -LiteralPath $frontendHtml -Raw -Encoding UTF8
$multiConditionEnabled = $frontendContent.Contains($multiConditionMarker)
$isolatedWs8769Enabled = $multiConditionEnabled -and -not $frontendContent.Contains("get('ws_port') || '8768'")

function Wait-Port {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($found -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

function Invoke-HttpWithRetry {
    param([string]$Uri, [int]$Attempts = 5)
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

function Test-TaskRunning {
    param($Task)
    return @('Running', '4') -contains [string]$Task.State
}

function Test-TaskOperational {
    param($Task)
    return @('Ready', 'Running', '3', '4') -contains [string]$Task.State
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$listener8094Before = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$process8094Before = if ($listener8094Before) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$($listener8094Before.OwningProcess)" -ErrorAction Stop
} else { $null }
$parent8094Before = if ($process8094Before) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$($process8094Before.ParentProcessId)" -ErrorAction SilentlyContinue
} else { $null }
$orphanPreviewProcesses = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
    if (
        -not $_.CommandLine -or
        (-not $_.CommandLine.Contains($expectedCommandPart) -and -not $_.CommandLine.Contains($legacyCommandPart))
    ) { return $false }
    $candidateParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.ParentProcessId)" -ErrorAction SilentlyContinue
    $listens8093 = Get-NetTCPConnection -LocalPort 8093 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1
    $listens8094 = Get-NetTCPConnection -LocalPort 8094 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1
    -not $candidateParent -and -not $listens8093 -and -not $listens8094
})
$removedOrphanPids = @()
$listener8093Before = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$listener8768Before = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$listener8769Before = Get-NetTCPConnection -LocalPort 8769 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$listener8770Before = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$listener11434Before = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
$process8769Before = if ($listener8769Before) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$($listener8769Before.OwningProcess)" -ErrorAction SilentlyContinue
} else { $null }
$before = [ordered]@{
    TaskState = $task.State.ToString()
    Port8093 = [bool]$listener8093Before
    Port8094 = [bool]$listener8094Before
    Port8768 = [bool]$listener8768Before
    Port8769 = [bool]$listener8769Before
    Port8770 = [bool]$listener8770Before
    Port11434 = [bool]$listener11434Before
    Process8093 = $listener8093Before.OwningProcess
    Process8094 = $listener8094Before.OwningProcess
    Process8768 = $listener8768Before.OwningProcess
    Process8769 = $listener8769Before.OwningProcess
    Process8770 = $listener8770Before.OwningProcess
    Process11434 = $listener11434Before.OwningProcess
}
if (
    -not (Test-TaskOperational $task) -or -not $before.Port8094 -or
    -not $before.Port8768 -or -not $before.Port8770 -or -not $before.Port11434
) {
    throw "8094 task and required protected ports must be healthy before restart"
}
if (
    -not $process8094Before -or $process8094Before.Name -ne "python.exe" -or
    (
        -not $process8094Before.CommandLine.Contains($expectedCommandPart) -and
        -not $process8094Before.CommandLine.Contains($legacyCommandPart)
    ) -or
    -not $parent8094Before -or -not $parent8094Before.CommandLine.Contains("run_22012_8094_preview.ps1")
) {
    throw "8094 listener is not owned by the expected managed preview task"
}
if ($isolatedWs8769Enabled -and $process8769Before -and -not $process8769Before.CommandLine.Contains($wsLauncherCommandPart)) {
    throw "8769 listener is not owned by the 8094 preview supervisor"
}

try {
    foreach ($orphan in $orphanPreviewProcesses) {
        Stop-Process -Id $orphan.ProcessId -Force
        $removedOrphanPids += [int]$orphan.ProcessId
    }
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    Start-Sleep -Seconds 1
    $stillListening = Get-NetTCPConnection -LocalPort 8094 -State Listen -OwningProcess $listener8094Before.OwningProcess -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($stillListening) {
        $stillProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($stillListening.OwningProcess)" -ErrorAction Stop
        if (
            $stillProcess.Name -ne "python.exe" -or
            (
                -not $stillProcess.CommandLine.Contains($expectedCommandPart) -and
                -not $stillProcess.CommandLine.Contains($legacyCommandPart)
            )
        ) {
            throw "Refusing to stop an unexpected process that owns port 8094"
        }
        Stop-Process -Id $stillListening.OwningProcess -Force
    }
    $still8769 = Get-NetTCPConnection -LocalPort 8769 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($isolatedWs8769Enabled -and $still8769) {
        $still8769Process = Get-CimInstance Win32_Process -Filter "ProcessId=$($still8769.OwningProcess)" -ErrorAction Stop
        if (-not $still8769Process.CommandLine.Contains($wsLauncherCommandPart)) {
            throw "Refusing to stop an unexpected process that owns port 8769"
        }
        Stop-Process -Id $still8769.OwningProcess -Force
        Wait-Port -Port 8769 -Listening $false -TimeoutSeconds 30
    }
    $exitDeadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $oldProcessExists = [bool](Get-CimInstance Win32_Process -Filter "ProcessId=$($listener8094Before.OwningProcess)" -ErrorAction SilentlyContinue)
        if (-not $oldProcessExists) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $exitDeadline)
    if ($oldProcessExists) { throw "Old 8094 listener PID did not exit" }
    if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8768 stopped unexpectedly during 8094 restart"
    }
    if (-not (Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "8770 stopped unexpectedly during 8094 restart"
    }
    if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        throw "11434 stopped unexpectedly during 8094 restart"
    }

    if (-not (Test-TaskRunning (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName))) {
        Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    }
    Wait-Port -Port 8094 -Listening $true -TimeoutSeconds 300
    if ($isolatedWs8769Enabled) { Wait-Port -Port 8769 -Listening $true -TimeoutSeconds 120 }
    Start-Sleep -Seconds 3
    $response = Invoke-HttpWithRetry -Uri "http://127.0.0.1:8094/?t=restart-$(Get-Date -Format yyyyMMddHHmmss)#overview"
    if ($response.StatusCode -ne 200) { throw "8094 HTTP status is $($response.StatusCode)" }
    if (-not $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")) {
        throw "8094 HTTP is missing adaptive layout marker"
    }
    if (-not $response.Content.Contains("20260726-viewport-wheel-r8")) {
        throw "8094 HTTP is missing the current billboard viewport adapter version"
    }
    if (-not $response.Content.Contains("BUG-BF3D-CAD-BOTTOM-BAND-20260804")) {
        throw "8094 HTTP is missing the CAD bottom-band fix"
    }
    if (-not $response.Content.Contains($revisionMarker)) {
        throw "8094 HTTP is missing the R2 furnace panel-body gap fix"
    }
    if ($multiConditionEnabled -and -not $response.Content.Contains($multiConditionMarker)) {
        throw "8094 HTTP is missing the multi-condition preview marker"
    }
    if ($multiConditionEnabled -and
        -not $response.Content.Contains("get('ws_port') || '8769'") -and
        -not $response.Content.Contains("get('ws_port') || '8768'")) {
        throw "8094 HTTP does not default to the shared 8768 or isolated 8769 WebSocket"
    }
    $listener8093After = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $listener8094After = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $listener8768After = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $listener8769After = Get-NetTCPConnection -LocalPort 8769 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $listener8770After = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $listener11434After = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $process8094After = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener8094After.OwningProcess)" -ErrorAction Stop
    if (
        $listener8094After.OwningProcess -eq $listener8094Before.OwningProcess -or
        $listener8768After.OwningProcess -ne $listener8768Before.OwningProcess -or
        ($isolatedWs8769Enabled -and $listener8769After.OwningProcess -eq $listener8769Before.OwningProcess) -or
        $listener8770After.OwningProcess -ne $listener8770Before.OwningProcess -or
        $listener11434After.OwningProcess -ne $listener11434Before.OwningProcess
    ) {
        throw "8094 restart did not replace its PID or unexpectedly changed a protected service"
    }
    $acceptedCommandParts = @($expectedCommandPart, $legacyCommandPart)
    if (-not ($acceptedCommandParts | Where-Object { $process8094After.CommandLine.Contains($_) })) {
        throw "8094 did not start the expected proxy after restart"
    }

    [ordered]@{
        RestartedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        RemovedOrphanPids = $removedOrphanPids
        Before = $before
        After = [ordered]@{
            TaskState = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
            Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
            Port8768 = [bool]$listener8768After
            Port8769 = [bool]$listener8769After
            Port8770 = [bool]$listener8770After
            Port11434 = [bool]$listener11434After
            Process8093ObservedBefore = if ($listener8093Before) { [int]$listener8093Before.OwningProcess } else { $null }
            Process8093ObservedAfter = if ($listener8093After) { [int]$listener8093After.OwningProcess } else { $null }
            Process8094Before = [int]$listener8094Before.OwningProcess
            Process8094After = [int]$listener8094After.OwningProcess
            Process8094Changed = $true
            Process8768Unchanged = $true
            Process8769Unchanged = (-not $isolatedWs8769Enabled)
            Process8769Changed = $isolatedWs8769Enabled
            Process8770Unchanged = $true
            Process11434Unchanged = $true
            HttpStatus = [int]$response.StatusCode
            HttpLength = $response.Content.Length
            HasAdaptiveFix = $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
            HasViewportWheelR8 = $response.Content.Contains("20260726-viewport-wheel-r8")
            HasCadBottomBandFix = $response.Content.Contains("BUG-BF3D-CAD-BOTTOM-BAND-20260804")
            HasCadPanelBodyGapFixR2 = $response.Content.Contains($revisionMarker)
            HasMultiConditionPreview = $response.Content.Contains($multiConditionMarker)
            HasDefaultWs8769 = $response.Content.Contains("get('ws_port') || '8769'")
            HasDefaultWs8768 = $response.Content.Contains("get('ws_port') || '8768'")
        }
    } | ConvertTo-Json -Depth 6
}
catch {
    if (-not (Test-TaskRunning (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName))) {
        Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    }
    throw
}
