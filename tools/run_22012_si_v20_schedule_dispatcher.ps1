$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'SiV20ScheduledShadowPrediction requires PowerShell 7 Core.'
}

$root = Split-Path -Parent $PSScriptRoot
$python = 'C:\Program Files\Python311\python.exe'
$script = Join-Path $root 'tools\run_si_v20_schedule_dispatcher.py'
$log = Join-Path $root 'logs\si_v20_schedule_dispatcher.log'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3.11 is unavailable' }
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Schedule dispatcher is unavailable' }
New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null

$startedAt = (Get-Date).ToString('o')
$output = & $python -X utf8 $script --base-url 'http://127.0.0.1:8093' 2>&1
$exitCode = $LASTEXITCODE
@("started_at=$startedAt") + $output | Add-Content -LiteralPath $log -Encoding UTF8
if ($exitCode -ne 0) { throw "V20 schedule dispatcher failed with exit code $exitCode" }
