param(
  [string]$HostAddress = "10.30.220.12",
  [string]$Model = "bf-diagnosis-runtime:v1",
  [string]$Question = "Please answer in one short sentence: who are you?",
  [int]$TimeoutSeconds = 180
)

$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Stop"

function Invoke-JsonPost {
  param(
    [string]$Url,
    [object]$Payload,
    [int]$TimeoutSec
  )
  $body = $Payload | ConvertTo-Json -Depth 12
  $sw = [Diagnostics.Stopwatch]::StartNew()
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec $TimeoutSec
    $sw.Stop()
    return [PSCustomObject]@{
      ok = $true
      elapsed_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 3)
      status_code = [int]$resp.StatusCode
      content_type = $resp.Headers["Content-Type"]
      body = $resp.Content
      error = ""
    }
  } catch {
    $sw.Stop()
    $detail = ""
    if ($_.Exception.Response) {
      try {
        $reader = [IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        $detail = $reader.ReadToEnd()
      } catch {
        $detail = ""
      }
    }
    return [PSCustomObject]@{
      ok = $false
      elapsed_seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 3)
      status_code = 0
      content_type = ""
      body = $detail
      error = $_.Exception.Message
    }
  }
}

Write-Host "== 1. Ollama service status =="
foreach ($url in @(
  "http://$HostAddress`:11434/api/version",
  "http://$HostAddress`:11434/api/tags",
  "http://$HostAddress`:8093/api/ollama/status"
)) {
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 15
    $body = $resp.Content
    if ($body.Length -gt 800) { $body = $body.Substring(0, 800) + "..." }
    Write-Host "[OK] $url status=$($resp.StatusCode)"
    Write-Host $body
  } catch {
    Write-Host "[FAIL] $url"
    Write-Host $_.Exception.Message
  }
}

Write-Host ""
Write-Host "== 2. Direct Ollama /api/chat test =="
$directPayload = @{
  model = $Model
  stream = $false
  messages = @(
    @{ role = "user"; content = $Question }
  )
  options = @{
    temperature = 0.2
    num_predict = 120
  }
}
$direct = Invoke-JsonPost -Url "http://$HostAddress`:11434/api/chat" -Payload $directPayload -TimeoutSec $TimeoutSeconds
$direct | ConvertTo-Json -Depth 6
$directBusinessOk = $direct.ok
if ($direct.ok) {
  try {
    $directObj = $direct.body | ConvertFrom-Json
    $directBusinessOk = [bool]($directObj.message.content)
  } catch {
    $directBusinessOk = $false
  }
}

Write-Host ""
Write-Host "== 3. 8093 page proxy /api/qa/chat test =="
$proxyPayload = @{
  message = $Question
  stream = $false
  current_snapshot = @{
    source = "manual_test"
    diagnosis = @{
      main_label = "normal"
      label = "normal"
    }
  }
}
$proxy = Invoke-JsonPost -Url "http://$HostAddress`:8093/api/qa/chat" -Payload $proxyPayload -TimeoutSec $TimeoutSeconds
$proxy | ConvertTo-Json -Depth 8
$proxyBusinessOk = $proxy.ok
if ($proxy.ok) {
  try {
    $proxyObj = $proxy.body | ConvertFrom-Json
    $proxyBusinessOk = ($proxyObj.ok -ne $false) -and [bool]$proxyObj.messages
  } catch {
    $proxyBusinessOk = $false
  }
}

Write-Host ""
Write-Host "== Result hint =="
if ($directBusinessOk -and -not $proxyBusinessOk) {
  Write-Host "Direct Ollama works, but 8093 proxy failed. Check 8093 proxy logs and Ollama server logs."
} elseif ($directBusinessOk -and $proxyBusinessOk) {
  Write-Host "Both direct Ollama and 8093 proxy returned a business-level success."
} elseif (-not $directBusinessOk) {
  Write-Host "Direct Ollama failed. Check BFOllama11434 service, GPU memory, and F:\Ollama\logs."
}
