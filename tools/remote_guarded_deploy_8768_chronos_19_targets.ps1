$ErrorActionPreference = 'Stop'

$serviceName = 'BFV4PreviewWs8768'
$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$targetPath = Join-Path $projectRoot '自动诊断服务\local_pg_ws_bridge.py'
$stagedPath = 'C:\Users\Administrator\AppData\Local\Temp\local_pg_ws_bridge_19.py'
$expectedBeforeHash = '5C17AEE8CFF9FE9C11828C5F854E5896FF061600416605838867BBB72122703D'
$expectedAfterHash = '798C55F262301D72168E775EB1B7AF128A6A08C6EAABCB4C0A99B8D76C8D6652'
$protectedPorts = @(5432, 8093, 8094, 8770, 8777, 11434)

function Get-ListenerPid {
    param([int]$Port)
    $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if (-not $connections) {
        return $null
    }
    return (@($connections | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique) -join ',')
}

function Wait-ServiceState {
    param([string]$Name, [string]$State, [int]$Seconds = 30)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction Stop
        if ($service.Status.ToString() -eq $State) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$Seconds = 30)
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $present = [bool](Get-ListenerPid -Port $Port)
        if ($present -eq $Listening) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

if (-not (Test-Path -LiteralPath $targetPath)) {
    throw "target bridge does not exist: $targetPath"
}
if (-not (Test-Path -LiteralPath $stagedPath)) {
    throw "staged bridge does not exist: $stagedPath"
}

$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetPath).Hash
$stagedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stagedPath).Hash
if ($beforeHash -ne $expectedBeforeHash) {
    throw "production bridge changed since probe: $beforeHash"
}
if ($stagedHash -ne $expectedAfterHash) {
    throw "staged bridge hash mismatch: $stagedHash"
}

$service = Get-Service -Name $serviceName -ErrorAction Stop
if ($service.Status -ne 'Running') {
    throw "$serviceName is not running before deployment"
}
if (-not (Get-ListenerPid -Port 8768)) {
    throw 'port 8768 is not listening before deployment'
}

$protectedBefore = [ordered]@{}
foreach ($port in $protectedPorts) {
    $pidValue = Get-ListenerPid -Port $port
    if (-not $pidValue) {
        throw "protected port is not listening before deployment: $port"
    }
    $protectedBefore[[string]$port] = $pidValue
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $projectRoot "backups\8768_chronos_19_targets_20260808\$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backupPath = Join-Path $backupDir 'local_pg_ws_bridge.py'
Copy-Item -LiteralPath $targetPath -Destination $backupPath -Force

$guardPaused = $false
$guardRestored = $false
$deployed = $false
$temporaryTarget = "$targetPath.codex_tmp"

try {
    Stop-Service -Name $serviceName -Force -ErrorAction Stop
    if (-not (Wait-ServiceState -Name $serviceName -State 'Stopped')) {
        throw "$serviceName did not stop"
    }
    if (-not (Wait-PortState -Port 8768 -Listening $false)) {
        throw 'port 8768 remained listening after service stop'
    }
    $guardPaused = $true

    Copy-Item -LiteralPath $stagedPath -Destination $temporaryTarget -Force
    Move-Item -LiteralPath $temporaryTarget -Destination $targetPath -Force
    $afterHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetPath).Hash
    if ($afterHash -ne $expectedAfterHash) {
        throw "deployed bridge hash mismatch: $afterHash"
    }
    $deployed = $true
}
finally {
    if (Test-Path -LiteralPath $temporaryTarget) {
        Remove-Item -LiteralPath $temporaryTarget -Force -ErrorAction SilentlyContinue
    }
    Start-Service -Name $serviceName -ErrorAction SilentlyContinue
    $serviceRunning = Wait-ServiceState -Name $serviceName -State 'Running'
    $portListening = Wait-PortState -Port 8768 -Listening $true
    $guardRestored = $serviceRunning -and $portListening
}

if (-not $deployed) {
    throw 'bridge deployment did not complete'
}
if (-not $guardRestored) {
    throw "$serviceName was not restored"
}

$protectedAfter = [ordered]@{}
foreach ($port in $protectedPorts) {
    $pidValue = Get-ListenerPid -Port $port
    $protectedAfter[[string]$port] = $pidValue
    if ($pidValue -ne $protectedBefore[[string]$port]) {
        throw "protected port PID changed: $port before=$($protectedBefore[[string]$port]) after=$pidValue"
    }
}

[pscustomobject]@{
    ok = $true
    service = $serviceName
    guard_paused = $guardPaused
    guard_restored = $guardRestored
    port_8768_pid = Get-ListenerPid -Port 8768
    before_hash = $beforeHash
    after_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetPath).Hash
    backup_path = $backupPath
    protected_before = $protectedBefore
    protected_after = $protectedAfter
} | ConvertTo-Json -Depth 5
