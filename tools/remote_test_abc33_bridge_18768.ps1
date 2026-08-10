$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$python = 'C:\Program Files\Python311\python.exe'
$candidate = Join-Path $root '自动诊断服务\local_pg_ws_bridge.candidate.py'
$auditStore = Join-Path $root '自动诊断服务\recommendation_audit_store.py'
$auditCandidate = Join-Path $root '自动诊断服务\recommendation_audit_store.candidate.py'
$auditBackup = Join-Path $root '自动诊断服务\recommendation_audit_store.candidate-test.bak'
$stdout = Join-Path $root 'logs\abc33_bridge_18768.out.log'
$stderr = Join-Path $root 'logs\abc33_bridge_18768.err.log'

if (-not (Test-Path -LiteralPath $candidate)) {
    throw "candidate bridge missing: $candidate"
}
if (-not (Test-Path -LiteralPath $auditCandidate)) {
    throw "candidate audit store missing: $auditCandidate"
}

foreach ($name in @('GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}
if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = '127.0.0.1' }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = '5432' }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = 'bf_trend' }
if ($env:GL02_PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:BF_WS_HOST = '127.0.0.1'
$env:BF_WS_PORT = '18768'
$env:BF_WS_HISTORY_HOURS = '8'
$env:BF_WS_TICK_SECONDS = '30'
$env:BF_CHRONOS_BASE_URL = 'http://127.0.0.1:8777'
$env:BF_CHRONOS_TIMEOUT_SECONDS = '900'

Remove-Item -LiteralPath $stdout -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stderr -Force -ErrorAction SilentlyContinue

$process = $null
$auditSwapped = $false
try {
    Copy-Item -LiteralPath $auditStore -Destination $auditBackup -Force
    Copy-Item -LiteralPath $auditCandidate -Destination $auditStore -Force
    $auditSwapped = $true
    $process = Start-Process -FilePath $python -ArgumentList @('-X', 'utf8', '-u', $candidate) -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    $listening = $false
    do {
        Start-Sleep -Seconds 1
        $process.Refresh()
        if ($process.HasExited) { break }
        $listener = Get-NetTCPConnection -LocalPort 18768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener -and $listener.OwningProcess -eq $process.Id) {
            $listening = $true
            break
        }
    } while ((Get-Date) -lt $deadline)

    $probeOutput = ''
    $probeExitCode = $null
    $payloadProbeOutput = ''
    $payloadProbeExitCode = $null
    if ($listening) {
        $payloadProbe = Join-Path $root 'tools\diagnose_candidate_bridge_payload.py'
        $payloadProbeOutput = (& $python -X utf8 $payloadProbe 2>&1) -join "`n"
        $payloadProbeExitCode = $LASTEXITCODE
        $probe = Join-Path $root 'tools\probe_abc33_ws_bundle.py'
        $probeOutput = (& $python -X utf8 $probe --url 'ws://127.0.0.1:18768' --timeout 120 2>&1) -join "`n"
        $probeExitCode = $LASTEXITCODE
    }

    [ordered]@{
        listening = $listening
        process_id = $process.Id
        exited = $process.HasExited
        exit_code = if ($process.HasExited) { $process.ExitCode } else { $null }
        stdout = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw -Encoding UTF8 } else { '' }
        stderr = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw -Encoding UTF8 } else { '' }
        probe_exit_code = $probeExitCode
        probe_output = $probeOutput
        payload_probe_exit_code = $payloadProbeExitCode
        payload_probe_output = $payloadProbeOutput
    } | ConvertTo-Json -Depth 4
    $global:LASTEXITCODE = 0
} finally {
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    if ($auditSwapped -and (Test-Path -LiteralPath $auditBackup)) {
        Copy-Item -LiteralPath $auditBackup -Destination $auditStore -Force
    }
}
