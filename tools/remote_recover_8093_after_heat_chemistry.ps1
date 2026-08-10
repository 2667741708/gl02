$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$config = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'BFV4PreviewProxy8093HealthCheck'

function Wait-Port8093([bool]$Listening, [int]$TimeoutSeconds = 90) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $present = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue)
        if ($present -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "8093 did not reach listening=$Listening"
}

$guardPaused = $false
try {
    Disable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
    Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    $guardPaused = $true
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $config | Out-Null
    Wait-Port8093 $false
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    Wait-Port8093 $true
    $health = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/qa/mcp/health' -TimeoutSec 30
    if ([int]$health.StatusCode -ne 200) { throw '8093 MCP health failed' }
} finally {
    if ($guardPaused) {
        Enable-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Out-Null
    }
}

[ordered]@{
    service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    listener_pid = [int](@(Get-NetTCPConnection -LocalPort 8093 -State Listen)[0].OwningProcess)
    http = [int]$health.StatusCode
    guard_state = (Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath).State.ToString()
} | ConvertTo-Json
