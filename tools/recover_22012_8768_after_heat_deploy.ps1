$ErrorActionPreference = "Continue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$service = Get-Service -Name "BFV4PreviewWs8768"
Write-Output ("status=" + $service.Status)
$listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) { Write-Output ("pid=" + $listener.OwningProcess) } else { Write-Output "pid=" }
$logPaths = @(
    ".\logs\ws_bridge_8768.err.log",
    ".\logs\local_pg_ws_bridge_8768.err.log",
    ".\logs\BFV4PreviewWs8768.err.log"
)
foreach ($path in $logPaths) {
    if (Test-Path -LiteralPath $path) {
        Write-Output ("log=" + $path)
        Get-Content -Tail 60 -LiteralPath $path
    }
}
if (-not $listener) {
    Start-Service -Name "BFV4PreviewWs8768" -ErrorAction Continue
    Start-Sleep -Seconds 8
    $listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { Write-Output ("recovered_pid=" + $listener.OwningProcess); exit 0 }
    Write-Output "recovered_pid="
    exit 2
}
