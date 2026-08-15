$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This operation requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-ABC33-BURDEN-THREE-FACTOR-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewWs8768'
$Python = 'C:\Program Files\Python311\python.exe'
$Probe = Join-Path $Root 'tools\probe_abc33_ws_bundle.py'
$ProtectedPorts = @(8093, 8094, 8770, 5432, 11434)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

function Get-ProtectedPortMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid -Port $Port }
    return $Map
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid -Port $Port) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening within $TimeoutSeconds seconds."
}

foreach ($Required in @($Python, $Probe)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing input: $Required" }
}
$ProtectedBefore = Get-ProtectedPortMap
foreach ($Key in $ProtectedBefore.Keys) {
    if (-not $ProtectedBefore[$Key]) { throw "Protected port $Key is not listening before 8768 restart." }
}
$Old8768Pid = Get-ListenerPid -Port 8768
if (-not $Old8768Pid -or (Get-Service -Name $ServiceName -ErrorAction Stop).Status -ne 'Running') {
    throw '8768 is not healthy before restart.'
}

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewWs8768Deployment')
$MutexAcquired = $false
$Restored = $false
try {
    $MutexAcquired = $Mutex.WaitOne(0)
    if (-not $MutexAcquired) { throw 'Another 8768 deployment or recovery owns the deployment mutex.' }
    Stop-Service -Name $ServiceName -Force
    Wait-PortState -Port 8768 -Listening $false -TimeoutSeconds 60
    Start-Service -Name $ServiceName
    Wait-PortState -Port 8768 -Listening $true -TimeoutSeconds 150
    $Restored = $true
    $New8768Pid = Get-ListenerPid -Port 8768
    if (-not $New8768Pid -or $New8768Pid -eq $Old8768Pid) { throw '8768 did not start with a new listener PID.' }

    $ProtectedAfter = Get-ProtectedPortMap
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedAfter[$Key] -ne $ProtectedBefore[$Key]) { throw "Protected PID changed during 8768 restart: $Key" }
    }

    $ProbeText = (& $Python -X utf8 $Probe --url 'ws://127.0.0.1:8768' --timeout 120 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "8768 WebSocket probe failed: $ProbeText" }
    $ProbeResult = $ProbeText | ConvertFrom-Json
    if ([int]$ProbeResult.rule_count -ne 33) { throw "8768 returned $($ProbeResult.rule_count) rules instead of 33." }
    $NeedsData = if ($ProbeResult.status_counts.needs_data) { [int]$ProbeResult.status_counts.needs_data } else { 0 }
    if ($NeedsData -eq 33) { throw 'All 33 rules still return needs_data.' }

    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=abc33-burden-rate-8768-$(Get-Date -Format yyyyMMddHHmmss)#optimization" -TimeoutSec 45
    if ($Page.StatusCode -ne 200) { throw '8093 HTTP failed after 8768 restart.' }

    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        service_restored = $Restored
        old_8768_pid = $Old8768Pid
        new_8768_pid = $New8768Pid
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        http_8093 = [int]$Page.StatusCode
        websocket = $ProbeResult
    } | ConvertTo-Json -Depth 9
}
finally {
    if (-not $Restored -and (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue).Status -ne 'Running') {
        Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
        Wait-PortState -Port 8768 -Listening $true -TimeoutSeconds 150
    }
    if ($MutexAcquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
