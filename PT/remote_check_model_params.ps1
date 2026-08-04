$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$models = @("bf-diagnosis-runtime:v1", "chiqiong-blast-furnace:latest")
foreach ($m in $models) {
  $body = @{ model = $m } | ConvertTo-Json -Compress
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/show" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 60
    $j = $r.Content | ConvertFrom-Json
    [pscustomobject]@{
      model = $m
      family = $j.details.family
      parameter_size = $j.details.parameter_size
      quantization_level = $j.details.quantization_level
      format = $j.details.format
      modified_at = $j.modified_at
    }
  } catch {
    [pscustomobject]@{ model = $m; error = $_.Exception.Message }
  }
}
