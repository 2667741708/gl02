$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$configPath = Join-Path $root "tools\service_configs\22012_BFOllama11434.json"
$manageScript = Join-Path $root "tools\manage_22012_managed_services.ps1"
$ollamaBaseUrl = "http://127.0.0.1:11434"
$chatModel = "chiqiong-blast-furnace:latest"
$embeddingModel = "nomic-embed-text"

function Invoke-JsonPost {
  param(
    [string]$Uri,
    [hashtable]$Payload,
    [int]$TimeoutSec = 240
  )
  $json = $Payload | ConvertTo-Json -Depth 20 -Compress
  Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json; charset=utf-8" -Body $json -TimeoutSec $TimeoutSec
}

function Wait-OllamaReady {
  param([int]$TimeoutSeconds = 180)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      Invoke-RestMethod -Method Get -Uri "$ollamaBaseUrl/api/version" -TimeoutSec 10 | Out-Null
      return
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)
  throw "Ollama did not become ready within $TimeoutSeconds seconds."
}

function Measure-Step {
  param(
    [string]$Name,
    [scriptblock]$Block
  )
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $result = & $Block
  $sw.Stop()
  [pscustomobject]@{
    name = $Name
    elapsed_ms = [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
    result = $result
  }
}

if (-not (Test-Path -LiteralPath $configPath)) {
  throw "Ollama service config not found: $configPath"
}
if (-not (Test-Path -LiteralPath $manageScript)) {
  throw "Managed service script not found: $manageScript"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = "$configPath.bak_two_loaded_$stamp"
Copy-Item -LiteralPath $configPath -Destination $backupPath -Force

$json = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $json.env) {
  $json | Add-Member -MemberType NoteProperty -Name env -Value ([pscustomobject]@{})
}
if ($json.env.PSObject.Properties.Name -contains "OLLAMA_MAX_LOADED_MODELS") {
  $json.env.OLLAMA_MAX_LOADED_MODELS = "2"
} else {
  $json.env | Add-Member -MemberType NoteProperty -Name OLLAMA_MAX_LOADED_MODELS -Value "2"
}
if ($json.env.PSObject.Properties.Name -contains "OLLAMA_KEEP_ALIVE") {
  $json.env.OLLAMA_KEEP_ALIVE = "24h"
} else {
  $json.env | Add-Member -MemberType NoteProperty -Name OLLAMA_KEEP_ALIVE -Value "24h"
}
if ($json.health -and $json.health.httpPost) {
  foreach ($post in @($json.health.httpPost)) {
    if ($post.json -and $post.json.PSObject.Properties.Name -contains "model") {
      $post.json.model = $chatModel
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

$json | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $configPath -Encoding UTF8

& powershell -NoProfile -ExecutionPolicy Bypass -File $manageScript -Action restart -ConfigPath $configPath
Wait-OllamaReady -TimeoutSeconds 240

$embed = Measure-Step "warm_embedding" {
  Invoke-JsonPost -Uri "$ollamaBaseUrl/api/embed" -Payload @{
    model = $embeddingModel
    input = "8093 latency warmup"
    keep_alive = "24h"
  } -TimeoutSec 120 | Out-Null
  "ok"
}

$chat = Measure-Step "warm_27b" {
  Invoke-JsonPost -Uri "$ollamaBaseUrl/api/chat" -Payload @{
    model = $chatModel
    messages = @(@{ role = "user"; content = "ping" })
    stream = $false
    keep_alive = "24h"
    think = $false
    options = @{
      num_predict = 1
      temperature = 0
      think = $false
    }
  } -TimeoutSec 240 | Out-Null
  "ok"
}

$ps = Invoke-RestMethod -Method Get -Uri "$ollamaBaseUrl/api/ps" -TimeoutSec 30
$loadedNames = @($ps.models | ForEach-Object { $_.name })
if ($loadedNames -notcontains $chatModel) {
  throw "Expected $chatModel in /api/ps after warm-up, got: $($loadedNames -join ', ')"
}
if (-not (@($loadedNames | Where-Object { $_ -eq $embeddingModel -or $_ -eq "$embeddingModel`:latest" }))) {
  throw "Expected $embeddingModel in /api/ps after warm-up, got: $($loadedNames -join ', ')"
}

[pscustomobject]@{
  backup_path = $backupPath
  config_path = $configPath
  ollama_max_loaded_models = "2"
  embedding = $embed
  chat = $chat
  loaded_models = $ps.models
} | ConvertTo-Json -Depth 20
