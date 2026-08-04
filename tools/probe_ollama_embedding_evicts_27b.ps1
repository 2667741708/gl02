param(
  [string]$BaseUrl = "http://10.30.220.12:11434",
  [string]$ChatModel = "chiqiong-blast-furnace:latest",
  [string]$EmbeddingModel = "nomic-embed-text"
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Post-Json {
  param(
    [string]$Uri,
    [hashtable]$Payload,
    [int]$TimeoutSec = 120
  )
  $json = $Payload | ConvertTo-Json -Depth 20 -Compress
  Invoke-RestMethod -Method Post -Uri $Uri -ContentType "application/json; charset=utf-8" -Body $json -TimeoutSec $TimeoutSec
}

function Get-LoadedModels {
  try {
    $ps = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/ps" -TimeoutSec 20
    @($ps.models) | ForEach-Object {
      [pscustomobject]@{
        name = $_.name
        size_vram = $_.size_vram
        expires_at = $_.expires_at
      }
    }
  } catch {
    @([pscustomobject]@{ error = $_.Exception.Message })
  }
}

function Measure-Block {
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

$before = Get-LoadedModels

$embed = Measure-Block "embed" {
  Post-Json -Uri "$BaseUrl/api/embed" -Payload @{
    model = $EmbeddingModel
    input = "8093 latency probe"
  } -TimeoutSec 120 | Out-Null
  "ok"
}

$afterEmbed = Get-LoadedModels

$chatWarm = Measure-Block "chat_warm_27b" {
  Post-Json -Uri "$BaseUrl/api/chat" -Payload @{
    model = $ChatModel
    stream = $false
    keep_alive = "24h"
    options = @{
      num_predict = 1
      temperature = 0
      think = $false
    }
    messages = @(
      @{
        role = "user"
        content = "ok"
      }
    )
  } -TimeoutSec 240 | Out-Null
  "ok"
}

$afterWarm = Get-LoadedModels

[pscustomobject]@{
  base_url = $BaseUrl
  chat_model = $ChatModel
  embedding_model = $EmbeddingModel
  before = $before
  embed = $embed
  after_embed = $afterEmbed
  chat_warm_27b = $chatWarm
  after_warm = $afterWarm
} | ConvertTo-Json -Depth 20
