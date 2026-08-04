$port = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$svc = Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewProxy8093'"
$status = $null
try {
  $status = (Invoke-WebRequest -Uri "http://127.0.0.1:8093/api/ollama/status" -UseBasicParsing -TimeoutSec 20).Content
} catch {
  $status = $_.Exception.Message
}

$procInfo = $null
$parentInfo = $null
if ($port) {
  $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($port.OwningProcess)" |
    Select-Object ProcessId, ParentProcessId, Name, CommandLine, ExecutablePath
  if ($procInfo.ParentProcessId) {
    $parentInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($procInfo.ParentProcessId)" |
      Select-Object ProcessId, ParentProcessId, Name, CommandLine, ExecutablePath
  }
}

[pscustomobject]@{
  Service = $svc | Select-Object Name, State, StartMode, ProcessId, PathName
  Port8093 = $port | Select-Object LocalAddress, LocalPort, OwningProcess
  ListenerProcess = $procInfo
  ParentProcess = $parentInfo
  Status = $status
} | ConvertTo-Json -Depth 6
