$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Chrome executable not found"
}

$python = "C:\Program Files\Python311\python.exe"
$verifier = Join-Path $projectRoot ".codex_stage\8093_near_plane_fix_20260801\verify_remote_8093_furnace_body_no_simulation.py"
$outDir = Join-Path $projectRoot "logs\acceptance\8093_near_plane_fix_20260801_r8"
$profile = "F:\bf8093_near_plane_accept_20260801_r8"
$debugPort = 9237

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python311 executable not found"
}
if (-not (Test-Path -LiteralPath $verifier)) {
    throw "Staged verifier not found: $verifier"
}
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
New-Item -ItemType Directory -Path $profile -Force | Out-Null

$chromeArgs = @(
    "--headless=new",
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$debugPort",
    "--remote-allow-origins=http://127.0.0.1",
    "--user-data-dir=$profile",
    "--no-first-run",
    "--disable-default-apps",
    "--disable-background-networking",
    "--ignore-gpu-blocklist",
    "--enable-webgl",
    "--use-angle=swiftshader",
    "about:blank"
)
$chromeProcess = Start-Process -FilePath $chrome -ArgumentList $chromeArgs -WindowStyle Hidden -PassThru

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:$debugPort/json/version" -TimeoutSec 1
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if (-not $ready) {
        throw "Chrome CDP port did not become ready"
    }

    & $python -X utf8 $verifier `
        --cdp "http://127.0.0.1:$debugPort" `
        --url "http://127.0.0.1:8093/?ws_port=8768&near_plane_acceptance=20260801_r4#overview" `
        --out-dir $outDir `
        --ready-timeout 50 `
        --skip-page-screenshots `
        --skip-canvas-screenshots `
        --skip-viewport-matrix
    if ($LASTEXITCODE -ne 0) {
        throw "8093 browser acceptance failed with exit code $LASTEXITCODE"
    }
} finally {
    Get-CimInstance -ClassName Win32_Process |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains("--user-data-dir=$profile") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $profile) {
        $resolvedProfile = (Resolve-Path -LiteralPath $profile).Path
        if ($resolvedProfile -eq "F:\bf8093_near_plane_accept_20260801_r8") {
            Remove-Item -LiteralPath $resolvedProfile -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
