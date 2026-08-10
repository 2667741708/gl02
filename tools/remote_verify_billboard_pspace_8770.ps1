$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$verifyScript = 'C:\Users\Administrator\AppData\Local\Temp\verify_billboard_pspace_8770.py'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'C:\Program Files\Python311\python.exe' }

foreach ($url in 'ws://127.0.0.1:8768', 'ws://127.0.0.1:8770') {
    & $python -X utf8 $verifyScript `
        --url $url `
        --open-timeout 10 `
        --frame-timeout 20 `
        --require-numeric 100
    if ($LASTEXITCODE -ne 0) {
        throw "$url WebSocket verification failed with exit code $LASTEXITCODE"
    }
}
