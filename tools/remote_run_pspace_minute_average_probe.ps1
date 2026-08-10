$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$probe = 'C:\Users\Administrator\AppData\Local\Temp\probe_pspace_minute_average_payload.py'
$rawModule = 'C:\Users\Administrator\AppData\Local\Temp\raw_minute_pipeline_candidate.py'

foreach ($name in 'PSPACE_SERVER', 'PSPACE_PORT', 'PSPACE_USER', 'PSPACE_PASSWORD', 'PSPACE_SDK_ROOT') {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, 'User')
    }
    if (-not $value) {
        $systemEnvironment = Get-ItemProperty -LiteralPath 'Registry::HKEY_USERS\S-1-5-18\Environment' -ErrorAction SilentlyContinue
        if ($systemEnvironment) {
            $value = $systemEnvironment.$name
        }
    }
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = 'C:\Program Files\Python311\python.exe'
}

$ErrorActionPreference = 'Continue'
$probeOutput = & $python -X utf8 $probe `
    --project-root $projectRoot `
    --raw-module $rawModule `
    --minutes 4 `
    --batch-size 133 2>&1
$probeExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$probeText = ($probeOutput | ForEach-Object { [string]$_ }) -join "`n"
$jsonStart = $probeText.IndexOf('{')
$jsonEnd = $probeText.LastIndexOf('}')
if ($jsonStart -lt 0 -or $jsonEnd -lt $jsonStart) {
    throw "pSpace minute-average probe did not return JSON (exit=$probeExitCode)"
}
$payload = $probeText.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
$payload | ConvertTo-Json -Depth 8
if ($probeExitCode -ne 0) {
    throw "pSpace minute-average probe failed with exit code $probeExitCode"
}
