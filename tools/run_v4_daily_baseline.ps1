$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = 'C:\Program Files\Python311\python.exe'
$script = Get-ChildItem -LiteralPath $root -Directory | ForEach-Object {
    $candidate = Join-Path $_.FullName 'baseline_maintainer.py'
    if (Test-Path -LiteralPath $candidate) { Get-Item -LiteralPath $candidate }
} | Select-Object -First 1
if (-not $script) { throw "V4 baseline maintainer was not found below $root" }
$script = $script.FullName
$config = Join-Path (Split-Path -Parent $script) 'config.yaml'
$verify = Join-Path $PSScriptRoot 'verify_abc33_baseline_coverage.py'
$day = (Get-Date).Date.ToString('yyyy-MM-dd')
if (-not (Test-Path -LiteralPath $script)) { throw "V4 baseline maintainer missing: $script" }
if (-not (Test-Path -LiteralPath $config)) { throw "V4 baseline config missing: $config" }
if (-not (Test-Path -LiteralPath $verify)) { throw "ABC33 baseline verifier missing: $verify" }

# Step 1: Build today's complete 30-day baseline set, including all
# ABC33 raw sources, derived series and the 80 furnace-body points.
& $python -X utf8 $script --build-day $day --baseline-days 30 --write --config $config
if ($LASTEXITCODE -ne 0) { throw "V4 baseline maintainer (full) failed with exit code $LASTEXITCODE" }

# Step 2: Fail closed when any ABC33 source/derived baseline is absent,
# statistically invalid, or below its effective 75% policy coverage.
& $python -X utf8 $verify --day $day --minimum-coverage 0.75
if ($LASTEXITCODE -ne 0) { throw "ABC33 daily baseline quality gate failed with exit code $LASTEXITCODE" }
