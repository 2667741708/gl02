$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$configPath = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\service_configs\22012_BFOllama11434.json"
$ollamaBaseUrl = "http://127.0.0.1:11434"
$modelName = "chiqiong-blast-furnace:latest"

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Ollama service config not found: $configPath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$configPath.bak_model_$stamp"
Copy-Item -LiteralPath $configPath -Destination $backupPath -Force

$json = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($json.health -and $json.health.httpPost) {
  foreach ($post in @($json.health.httpPost)) {
    if ($post.json -and $post.json.PSObject.Properties.Name -contains "model") {
      $post.json.model = $modelName
    }
    if ($post.json) {
      if ($post.json.PSObject.Properties.Name -contains "keep_alive") {
        $post.json.keep_alive = "24h"
      } else {
        $post.json | Add-Member -MemberType NoteProperty -Name keep_alive -Value "24h"
      }
      if ($post.json.PSObject.Properties.Name -contains "think") {
        $post.json.think = $false
      } else {
        $post.json | Add-Member -MemberType NoteProperty -Name think -Value $false
      }
      if ($post.json.options) {
        if ($post.json.options.PSObject.Properties.Name -contains "think") {
          $post.json.options.think = $false
        } else {
          $post.json.options | Add-Member -MemberType NoteProperty -Name think -Value $false
        }
      }
    }
  }
}

$json | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $configPath -Encoding UTF8

$warmPayload = @{
  model = $modelName
  messages = @(@{ role = "user"; content = "ping" })
  stream = $false
  keep_alive = "24h"
  think = $false
  options = @{
    num_predict = 1
    temperature = 0
    think = $false
  }
} | ConvertTo-Json -Depth 8 -Compress

$warmStart = Get-Date
$warm = Invoke-WebRequest -Uri "$ollamaBaseUrl/api/chat" -Method Post -Body $warmPayload -ContentType "application/json; charset=utf-8" -UseBasicParsing -TimeoutSec 240
$warmMs = [int](((Get-Date) - $warmStart).TotalMilliseconds)

$ps = Invoke-WebRequest -Uri "$ollamaBaseUrl/api/ps" -UseBasicParsing -TimeoutSec 30
$psText = $ps.Content
if ($psText -notlike "*$modelName*") {
  throw "Expected $modelName in /api/ps after warm-up, got: $psText"
}

[pscustomobject]@{
  BackupPath = $backupPath
  WarmupMilliseconds = $warmMs
  OllamaPs = ($psText | ConvertFrom-Json)
} | ConvertTo-Json -Depth 8
