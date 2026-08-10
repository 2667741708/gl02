$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$service = "BFV4PreviewWs8768"

function Get-Pid([int]$Port) {
    $item = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($item) { return [int]$item.OwningProcess }
    return $null
}
function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $present = $null -ne (Get-Pid $Port)
        if ($present -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port did not reach listening=$Listening"
}

$before = @{
    p8093 = Get-Pid 8093; p8094 = Get-Pid 8094; p8768 = Get-Pid 8768;
    p8770 = Get-Pid 8770; p11434 = Get-Pid 11434
}
if (-not $before.p8093 -or -not $before.p8094 -or -not $before.p8768 -or -not $before.p8770 -or -not $before.p11434) { throw "Protected listener precondition failed" }
$stopped = $false
try {
    Stop-Service -Name $service -Force
    $stopped = $true
    Wait-Port 8768 $false 90
    Start-Service -Name $service
    $stopped = $false
    Wait-Port 8768 $true 150
    $after = @{
        p8093 = Get-Pid 8093; p8094 = Get-Pid 8094; p8768 = Get-Pid 8768;
        p8770 = Get-Pid 8770; p11434 = Get-Pid 11434
    }
    if ($after.p8093 -ne $before.p8093 -or $after.p8094 -ne $before.p8094 -or $after.p8770 -ne $before.p8770 -or $after.p11434 -ne $before.p11434) { throw "Protected PID changed during 8768 restart" }
    $http = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 30
    if ([int]$http.StatusCode -ne 200) { throw "8094 HTTP status is not 200" }
    [ordered]@{ ok = $true; before = $before; after = $after; http8094 = [int]$http.StatusCode } | ConvertTo-Json -Depth 5
} catch {
    if ($stopped -and (Get-Service -Name $service).Status -ne "Running") { Start-Service -Name $service -ErrorAction SilentlyContinue }
    throw
}
