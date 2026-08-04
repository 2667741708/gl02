$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$expectedCommandPart = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server.py"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

$connection = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
$listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction Stop
$listenerParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerProcess.ParentProcessId)" -ErrorAction SilentlyContinue
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$orphans = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    if (-not $_.CommandLine -or -not $_.CommandLine.Contains($expectedCommandPart)) { return $false }
    $candidateParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.ParentProcessId)" -ErrorAction SilentlyContinue
    $listens8093 = Get-NetTCPConnection -LocalPort 8093 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1
    $listens8094 = Get-NetTCPConnection -LocalPort 8094 -State Listen -OwningProcess $_.ProcessId -ErrorAction SilentlyContinue | Select-Object -First 1
    -not $candidateParent -and -not $listens8093 -and -not $listens8094
})

if ($listenerProcess.Name -ne "python.exe" -or -not $listenerProcess.CommandLine.Contains($expectedCommandPart)) {
    throw "8094 listener is not the expected V4 preview Python process"
}
if (-not $listenerParent -or -not $listenerParent.CommandLine.Contains("run_22012_8094_preview.ps1")) {
    throw "Current 8094 listener is not owned by the managed preview task"
}
if ($orphans.Count -ne 1) {
    throw "Expected exactly one non-listening orphan preview process, found $($orphans.Count)"
}
$process = $orphans[0]
$stalePid = $process.ProcessId
if ($task.State -ne "Running") {
    throw "8094 preview task is not running; refusing orphan cleanup"
}
if (-not (Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw "8093 is not listening before orphan cleanup"
}
if (-not (Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw "8768 is not listening before orphan cleanup"
}

Stop-Process -Id $stalePid -Force
$newConnection = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop | Select-Object -First 1
if ($newConnection.OwningProcess -ne $listenerProcess.ProcessId) { throw "8094 listener changed during orphan cleanup" }

$newProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($newConnection.OwningProcess)" -ErrorAction Stop
$newParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($newProcess.ParentProcessId)" -ErrorAction SilentlyContinue
if ($newProcess.Name -ne "python.exe" -or -not $newProcess.CommandLine.Contains($expectedCommandPart)) {
    throw "Fresh 8094 listener is not the expected V4 preview process"
}
if (-not $newParent -or -not $newParent.CommandLine.Contains("run_22012_8094_preview.ps1")) {
    throw "Fresh 8094 listener is not owned by the managed preview task"
}

Start-Sleep -Seconds 3
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?t=orphan-cleanup-$(Get-Date -Format yyyyMMddHHmmss)#overview" -TimeoutSec 60
if ($response.StatusCode -ne 200 -or -not $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")) {
    throw "Fresh 8094 listener failed HTTP marker verification"
}

[ordered]@{
    CleanedAt = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Removed = [ordered]@{
        ProcessId = $stalePid
        CreationDate = $process.CreationDate.ToString("yyyy-MM-dd HH:mm:ss")
        ParentProcessId = $process.ParentProcessId
        ParentWasMissing = $true
    }
    Fresh = [ordered]@{
        ProcessId = $newProcess.ProcessId
        CreationDate = $newProcess.CreationDate.ToString("yyyy-MM-dd HH:mm:ss")
        ParentProcessId = $newProcess.ParentProcessId
        ParentCommandLine = $newParent.CommandLine
    }
    Runtime = [ordered]@{
        Preview8094Task = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
        Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        Port8094 = [bool](Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
        HttpStatus = [int]$response.StatusCode
        HasAdaptiveFix = $response.Content.Contains("BUG-8093-OVERVIEW-ADAPTIVE-CLIP-20260716")
    }
} | ConvertTo-Json -Depth 8
