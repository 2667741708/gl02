$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$serviceName = 'BFV4PreviewProxy8093'
$guardTaskName = 'BFV4PreviewProxy8093HealthCheck'
$guardTaskPath = '\BlastFurnaceServices\'
$manager = Get-ChildItem -LiteralPath $root -Filter 'manage_22012_managed_services.ps1' -File -Recurse | Select-Object -First 1 -ExpandProperty FullName
$config = Get-ChildItem -LiteralPath $root -Filter '22012_BFV4PreviewProxy8093.json' -File -Recurse | Select-Object -First 1 -ExpandProperty FullName
$mcp = Get-ChildItem -LiteralPath $root -Filter 'bf_data_mcp_server.py' -File -Recurse | Where-Object { $_.FullName -like '*\mcp\bf_data_mcp_server.py' } | Select-Object -First 1 -ExpandProperty FullName
$python = 'C:\Program Files\Python311\python.exe'
foreach ($path in @($manager, $config, $mcp, $python)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "missing required path: $path" } }

& $python -m py_compile $mcp
if ($LASTEXITCODE -ne 0) { throw 'MCP compile failed before restart' }
$mcpText = Get-Content -LiteralPath $mcp -Raw -Encoding UTF8
if ($mcpText -notmatch 'def query_bf2_operation_log_report\(') { throw 'report MCP tool marker missing' }

function ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return $null
}
function WaitState([string]$State, [bool]$Listening) {
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        $service = Get-Service -Name $serviceName
        $ready = $service.Status.ToString() -eq $State
        $portReady = ($null -ne (ListenerPid 8093)) -eq $Listening
        if ($ready -and $portReady) { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "service/listener did not reach $State/$Listening"
}

$before = @{}
foreach ($port in @(8768, 8094, 8770)) { $before[[string]$port] = ListenerPid $port }
$guardPaused = $false
try {
    Disable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null
    Stop-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath -ErrorAction SilentlyContinue
    $guardPaused = $true
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $config | Out-Null
    WaitState 'Stopped' $false
    foreach ($port in @(8768, 8094, 8770)) { if ((ListenerPid $port) -ne $before[[string]$port]) { throw "protected port changed while stopped: $port" } }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $config | Out-Null
    WaitState 'Running' $true
} finally {
    if ($guardPaused) { Enable-ScheduledTask -TaskName $guardTaskName -TaskPath $guardTaskPath | Out-Null }
}

$after = @{}
foreach ($port in @(8768, 8094, 8770)) { $after[[string]$port] = ListenerPid $port; if ($after[[string]$port] -ne $before[[string]$port]) { throw "protected port PID changed: $port" } }
$response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 30
if ([int]$response.StatusCode -ne 200) { throw '8093 HTTP status is not 200' }
Get-ScheduledTaskInfo -TaskName $guardTaskName -TaskPath $guardTaskPath | Select-Object LastRunTime,LastTaskResult,NextRunTime
Write-Output "report_mcp_restart_ok=true"

