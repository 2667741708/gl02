$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$serviceName = "BFV4PreviewProxy8093"
$configPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFV4PreviewProxy8093.json"
$modelName = "chiqiong-blast-furnace:latest"
$publicModelName = "炽穹·高炉炼铁大模型"
$ollamaBaseUrl = "http://127.0.0.1:11434"

function Set-ArgumentValue {
  param(
    [object]$Config,
    [string]$Name,
    [string]$Value
  )
  $args = [System.Collections.Generic.List[string]]::new()
  foreach ($item in @($Config.arguments)) {
    [void]$args.Add([string]$item)
  }
  $index = $args.IndexOf($Name)
  if ($index -ge 0) {
    if ($index + 1 -lt $args.Count) {
      $args[$index + 1] = $Value
    } else {
      [void]$args.Add($Value)
    }
  } else {
    [void]$args.Add($Name)
    [void]$args.Add($Value)
  }
  $Config.arguments = @($args)
}

function Wait-PortReleased {
  param([int]$Port, [int]$Seconds = 20)
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $true }
    Start-Sleep -Milliseconds 500
  }
  return -not [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Stop-PreviewPortProcess {
  $conn = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $conn) { return }
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
  if (-not $proc -or $proc.CommandLine -notlike "*V4_8093_PREVIEW*") {
    throw "Refusing to stop unrelated 8093 listener: PID=$($conn.OwningProcess) CommandLine=$($proc.CommandLine)"
  }
  $parent = $null
  if ($proc.ParentProcessId) {
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue
  }
  Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
  if ($parent -and $parent.CommandLine -like "*V4_8093_PREVIEW*" -and $parent.CommandLine -like "*start_v3_8092_python.py*") {
    Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "8093 service config not found: $configPath"
}

$showBody = @{ name = $modelName } | ConvertTo-Json -Compress
$show = Invoke-WebRequest -Uri "$ollamaBaseUrl/api/show" -Method Post -Body $showBody -ContentType "application/json" -UseBasicParsing -TimeoutSec 30
if ($show.StatusCode -ne 200) {
  throw "Ollama model check failed for $modelName"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$configPath.bak_model_$stamp"
Copy-Item -LiteralPath $configPath -Destination $backupPath -Force

$json = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $json.env) {
  $json | Add-Member -MemberType NoteProperty -Name env -Value ([pscustomobject]@{})
}

if ($json.env.PSObject.Properties.Name -contains "BF_LLM_MODEL") {
  $json.env.BF_LLM_MODEL = $modelName
} else {
  $json.env | Add-Member -MemberType NoteProperty -Name BF_LLM_MODEL -Value $modelName
}

if ($json.env.PSObject.Properties.Name -contains "BF_PUBLIC_MODEL_NAME") {
  $json.env.BF_PUBLIC_MODEL_NAME = $publicModelName
} else {
  $json.env | Add-Member -MemberType NoteProperty -Name BF_PUBLIC_MODEL_NAME -Value $publicModelName
}

if ($json.env.PSObject.Properties.Name -contains "OLLAMA_BASE_URL") {
  $json.env.OLLAMA_BASE_URL = $ollamaBaseUrl
} else {
  $json.env | Add-Member -MemberType NoteProperty -Name OLLAMA_BASE_URL -Value $ollamaBaseUrl
}

Set-ArgumentValue -Config $json -Name "--ollama-base-url" -Value $ollamaBaseUrl
Set-ArgumentValue -Config $json -Name "--model" -Value $modelName
Set-ArgumentValue -Config $json -Name "--public-model" -Value $publicModelName

$json | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $configPath -Encoding UTF8

Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Stop-PreviewPortProcess
if (-not (Wait-PortReleased -Port 8093 -Seconds 20)) {
  Stop-PreviewPortProcess
  if (-not (Wait-PortReleased -Port 8093 -Seconds 10)) {
    throw "8093 port is still listening after stopping preview processes"
  }
}

Start-Service -Name $serviceName
Start-Sleep -Seconds 12

$svc = Get-Service -Name $serviceName
$port = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$statusRaw = (Invoke-WebRequest -Uri "http://127.0.0.1:8093/api/ollama/status" -UseBasicParsing -TimeoutSec 45).Content
$status = $statusRaw | ConvertFrom-Json
$listener = $null
$listenerParent = $null
if ($port) {
  $listener = Get-CimInstance Win32_Process -Filter "ProcessId=$($port.OwningProcess)" |
    Select-Object ProcessId, ParentProcessId, CommandLine
  if ($listener.ParentProcessId) {
    $listenerParent = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.ParentProcessId)" -ErrorAction SilentlyContinue |
      Select-Object ProcessId, ParentProcessId, CommandLine
  }
}

if (-not $port) {
  throw "8093 is not listening after restart"
}
$listenerCommand = [string]($listener.CommandLine)
$listenerParentCommand = [string]($listenerParent.CommandLine)
$configArgs = [string]::Join(" ", @($json.arguments))
if (
  -not $status.ok -or
  -not $status.model_ok -or
  (
    $listenerCommand -notlike "*--model $modelName*" -and
    $listenerParentCommand -notlike "*--model $modelName*" -and
    $configArgs -notlike "*--model $modelName*"
  ) -or
  ($status.target_model -ne $modelName -and $status.target_model -ne $publicModelName)
) {
  throw "8093 model switch verification failed: $statusRaw"
}

[pscustomobject]@{
  Service = $svc.Name
  ServiceStatus = $svc.Status.ToString()
  Port8093 = [bool]$port
  RuntimeModel = $modelName
  PublicTargetModel = $status.target_model
  ModelOk = $status.model_ok
  Listener = $listener
  ListenerParent = $listenerParent
  BackupPath = $backupPath
} | ConvertTo-Json -Depth 4
