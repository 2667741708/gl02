$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$serviceName = "BFV4PreviewWs8768"
$taskPath = "\BlastFurnaceServices\"
$healthTask = "BFV4PreviewWs8768HealthCheck"
$health = Get-ScheduledTask -TaskPath $taskPath -TaskName $healthTask -ErrorAction Stop
if (-not $health.Settings.Enabled) {
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $healthTask | Out-Null
}

$lastError = $null
for ($attempt = 1; $attempt -le 12; $attempt++) {
    try { Start-Service -Name $serviceName -ErrorAction Stop }
    catch { $lastError = $_ }
    if ((Get-Service -Name $serviceName).Status -eq "Running") { break }
    Start-Sleep -Seconds 5
}
if ((Get-Service -Name $serviceName).Status -ne "Running") {
    Start-ScheduledTask -TaskPath $taskPath -TaskName $healthTask
}

$deadline = (Get-Date).AddSeconds(240)
do {
    $listener = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { break }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

if (-not $listener) {
    if ($lastError) { throw $lastError }
    throw "8768 recovery did not produce a listener"
}

[ordered]@{
    ok = $true
    service = [string](Get-Service -Name $serviceName).Status
    listenerPid = [int]$listener.OwningProcess
    healthTaskEnabled = [bool](Get-ScheduledTask -TaskPath $taskPath -TaskName $healthTask).Settings.Enabled
} | ConvertTo-Json -Depth 4
