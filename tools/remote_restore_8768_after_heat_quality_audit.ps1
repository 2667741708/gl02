$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

$protectedBefore = [ordered]@{
    port_8093 = Get-ListenerPid 8093
    port_8094 = Get-ListenerPid 8094
    port_8770 = Get-ListenerPid 8770
}
if ((Get-Service -Name 'BFV4PreviewWs8768').Status.ToString() -ne 'Running') {
    Start-Service -Name 'BFV4PreviewWs8768'
}
$deadline = [DateTime]::UtcNow.AddSeconds(60)
do {
    Start-Sleep -Milliseconds 250
    $serviceRunning = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString() -eq 'Running'
    $listener8768 = Get-ListenerPid 8768
} while ((-not $serviceRunning -or -not $listener8768) -and [DateTime]::UtcNow -lt $deadline)
if (-not $serviceRunning -or -not $listener8768) { throw '8768 did not recover' }
foreach ($port in @(8093, 8094, 8770)) {
    if ((Get-ListenerPid $port) -ne $protectedBefore["port_$port"]) {
        throw "Protected PID changed on port $port"
    }
}

[ordered]@{
    restored = $true
    service = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    pid_8768 = $listener8768
    protected_pids = $protectedBefore
} | ConvertTo-Json -Depth 5
