$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = Split-Path -Parent $PSScriptRoot
$python = 'C:\Program Files\Python311\python.exe'
$script = Join-Path $root 'tools\run_si_v20_hourly_prediction.py'
$log = Join-Path $root 'logs\si_v20_hourly_prediction.log'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3.11 is unavailable' }
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Hourly prediction runner is unavailable' }
New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null

$cutoff = (Get-Date).ToString('yyyy-MM-dd HH:00:00')
$output = & $python -X utf8 $script --base-url 'http://127.0.0.1:8093' --cutoff-ts $cutoff 2>&1
$exitCode = $LASTEXITCODE
$output | Add-Content -LiteralPath $log -Encoding UTF8
if ($exitCode -ne 0) { throw "V20 hourly prediction failed with exit code $exitCode" }
