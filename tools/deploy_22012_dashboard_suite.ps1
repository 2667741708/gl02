$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Output "=== 220.12 Dashboard Suite v2 $stamp ==="

# ============================================================
# PART A: Heat Dashboard (8891) - patch & restart
# ============================================================
Write-Output "[A] Heat Dashboard 8891"

$heatRoot = "$root\standalone_heat_dashboard_8891"
$heatTaskName = "StandaloneHeatDashboard8891"
$heatTaskPath = "\BlastFurnaceServices\"

if (Test-Path -LiteralPath $heatRoot) {
    # Patch heat_service.py with inline sed-like replacements
    $hs = "$heatRoot\db_dashboard\heat_service.py"
    if (Test-Path -LiteralPath $hs) {
        Copy-Item -LiteralPath $hs -Destination "$heatRoot\backups\heat_service_$stamp.py" -Force
        $c = Get-Content -LiteralPath $hs -Raw -Encoding UTF8

        # Fix 1: credential fallback
        if ($c -match '_setting\("IMES_OPS_DB_USER", file_values\)') {
            $c = $c -replace '_setting\("IMES_OPS_DB_USER", file_values\)', 'os.getenv("IMES_OPS_DB_USER") or file_values.get("IMES_OPS_DB_USER") or file_values.get("IMES_DB_USER")'
            $c = $c -replace '_setting\("IMES_OPS_DB_PASSWORD", file_values\)', 'os.getenv("IMES_OPS_DB_PASSWORD") or file_values.get("IMES_OPS_DB_PASSWORD") or file_values.get("IMES_DB_PASSWORD")'
            Write-Output "  heat_service.py: credential fallback applied"
        } else { Write-Output "  heat_service.py: fallback already in place" }

        # Fix 2: _vastbase_connect retry support
        if ($c -notmatch 'max_attempts = params.pop') {
            $c = $c -replace 'for attempt in range\(3\):', 'max_attempts = params.pop("_max_attempts", 3)`n    for attempt in range(max_attempts):'
            $c = $c -replace 'if attempt < 2:', 'if attempt < max_attempts - 1:'
            Write-Output "  heat_service.py: retry support applied"
        } else { Write-Output "  heat_service.py: retry already in place" }

        [IO.File]::WriteAllText($hs, $c, [Text.UTF8Encoding]::new($false))
    }

    # Patch external_sources.py
    $es = "$heatRoot\db_dashboard\external_sources.py"
    if (Test-Path -LiteralPath $es) {
        Copy-Item -LiteralPath $es -Destination "$heatRoot\backups\external_sources_$stamp.py" -Force
        $ec = Get-Content -LiteralPath $es -Raw -Encoding UTF8
        if ($ec -notmatch 'LEGACY_IMES_ENV\)\.get\("IMES_DB_PASSWORD"\)') {
            $ec = $ec -replace '\)_load_env_file\(EXTERNAL_ENV\)\.get\("IMES_OPS_DB_PASSWORD"\)\s+\)', '_load_env_file(EXTERNAL_ENV).get("IMES_OPS_DB_PASSWORD")`n                or _load_env_file(LEGACY_IMES_ENV).get("IMES_DB_PASSWORD")`n            )'
            Write-Output "  external_sources.py: catalog check patched"
        } else { Write-Output "  external_sources.py: already patched" }
        [IO.File]::WriteAllText($es, $ec, [Text.UTF8Encoding]::new($false))
    }

    # Restart via task
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*db_dashboard*server.py*" } |
        ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    $ht = Get-ScheduledTask -TaskPath $heatTaskPath -TaskName $heatTaskName -ErrorAction SilentlyContinue
    if ($ht -and $ht.State -ne 'Running') { Start-ScheduledTask -TaskPath $heatTaskPath -TaskName $heatTaskName }
    Write-Output "  Heat dashboard restarted (task: $(if($ht){$ht.State}else{'MISSING'}))"
} else {
    Write-Output "  SKIP: heat dashboard directory not found"
}

# ============================================================
# PART B: Foreman Trend (8892) - full deployment
# ============================================================
Write-Output "[B] Foreman Trend 8892"

$trendRoot = "$root\standalone_foreman_trend_8892"
$trendPort = 8892
$trendTaskName = "StandaloneForemanTrend8892"
$trendTaskPath = "\BlastFurnaceServices\"
$fwRuleName = "BlastFurnaceForemanTrend8892"

# B1. Create directories
foreach ($d in @("$trendRoot\tools", "$trendRoot\高炉前端数据\assets", "$trendRoot\高炉前端数据\libs", "$trendRoot\logs")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

# B2. Write the Python HTTP server
$pythonServer = @'
# -*- coding: utf-8 -*-
"""Lightweight HTTP server for the foreman trend preview page (port 8892)."""
from __future__ import annotations
import os, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=300")
        super().end_headers()
    def log_message(self, format, *args):
        print(f"[8892] {self.client_address[0]} - {format % args}", flush=True)

FRONTEND_DIR = Path(os.environ.get("BF_FRONTEND_DIR", Path(__file__).resolve().parents[1] / "高炉前端数据"))

if __name__ == "__main__":
    host = os.environ.get("BF_FOREMAN_HOST", "0.0.0.0")
    port = int(os.environ.get("BF_FOREMAN_PORT", "8892"))
    server = HTTPServer((host, port), Handler)
    print(f"[8892] serving {FRONTEND_DIR} on {host}:{port}", flush=True)
    server.serve_forever()
'@
[IO.File]::WriteAllText("$trendRoot\tools\foreman_trend_server.py", $pythonServer, [Text.UTF8Encoding]::new($false))
Write-Output "  server.py: written"

# B3. Write the runner PowerShell script
$runnerPs1 = @"
`$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new(`$false)
`$OutputEncoding = [Text.UTF8Encoding]::new(`$false)
`$root = "$trendRoot"
`$server = "`$root\tools\foreman_trend_server.py"
`$logDir = "`$root\logs"
`$log = "`$logDir\foreman_trend_8892.log"
New-Item -ItemType Directory -Force -Path `$logDir | Out-Null

foreach (`$name in "GL02_PGHOST","GL02_PGPORT","GL02_PGDATABASE","GL02_PGUSER","GL02_PGPASSWORD") {
    `$value = [Environment]::GetEnvironmentVariable(`$name, "Machine")
    if (`$value) { Set-Item -Path "Env:`$name" -Value `$value }
}

`$env:PYTHONIOENCODING = "utf-8"
`$env:PYTHONUTF8 = "1"
`$env:BF_FOREMAN_HOST = "0.0.0.0"
`$env:BF_FOREMAN_PORT = "8892"
`$env:BF_FRONTEND_DIR = "`$root\高炉前端数据"

if (-not (Test-Path -LiteralPath `$server)) {
    Add-Content -LiteralPath `$log -Encoding UTF8 -Value "`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') missing server"
    exit 2
}

while (`$true) {
    Add-Content -LiteralPath `$log -Encoding UTF8 -Value "`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') starting on 8892"
    Set-Location -LiteralPath `$root
    & "C:\Program Files\Python311\python.exe" -X utf8 -u `$server >> `$log 2>&1
    Add-Content -LiteralPath `$log -Encoding UTF8 -Value "`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exited `$LASTEXITCODE; restart in 5s"
    Start-Sleep -Seconds 5
}
"@
[IO.File]::WriteAllText("$trendRoot\run_22012_foreman_trend_8892.ps1", $runnerPs1, [Text.UTF8Encoding]::new($false))
Write-Output "  runner.ps1: written"

# B4. Copy frontend assets from main 8093 frontend directory
$srcFE = "$root\高炉前端数据"
$dstFE = "$trendRoot\高炉前端数据"
$needsUpload = $false

foreach ($asset in @("foreman_trend_preview.html", "assets\foreman-trend-preview.css", "assets\foreman-trend-preview.js")) {
    $src = Join-Path $srcFE $asset
    $dst = Join-Path $dstFE $asset
    if (Test-Path -LiteralPath $src) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Output "  copied: $asset"
    } else {
        Write-Output "  MISSING: $asset - needs upload"
        $needsUpload = $true
    }
}

# Copy echarts from existing lib if present
$echartsSrc = "$srcFE\libs\echarts.min.js"
$echartsDst = "$dstFE\libs\echarts.min.js"
if (Test-Path -LiteralPath $echartsSrc) {
    Copy-Item -LiteralPath $echartsSrc -Destination $echartsDst -Force
    Write-Output "  copied: libs/echarts.min.js"
} else {
    Write-Output "  MISSING: libs/echarts.min.js"
}

# B5. Firewall
if (-not (Get-NetFirewallRule -Name $fwRuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $fwRuleName -DisplayName $fwRuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $trendPort -Profile Domain,Private | Out-Null
    Write-Output "  firewall: created"
} else { Write-Output "  firewall: exists" }

# B6. Kill any old process
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*foreman_trend_server*" } |
    ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue }

# B7. Scheduled task
$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$runnerPath = "$trendRoot\run_22012_foreman_trend_8892.ps1"

Get-ScheduledTask -TaskPath $trendTaskPath -TaskName $trendTaskName -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-ScheduledTask -TaskPath $trendTaskPath -TaskName $trendTaskName -ErrorAction SilentlyContinue; Start-Sleep 1; Unregister-ScheduledTask -TaskPath $trendTaskPath -TaskName $trendTaskName -Confirm:$false -ErrorAction SilentlyContinue }

$action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $trendTaskPath -TaskName $trendTaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $trendTaskPath -TaskName $trendTaskName
Write-Output "  scheduled task: created & started"

# ============================================================
# PART C: Verify
# ============================================================
Write-Output "[C] Verify"
Start-Sleep -Seconds 5

foreach ($port in @(8891, 8892)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output "  Port $port : $(if($l){'LISTEN PID '+$l.OwningProcess}else{'NOT LISTENING'})"
}

foreach ($pair in @(
    @{Port=8891; Name="Heat"; Path="/api/overview"},
    @{Port=8892; Name="Trend"; Path="/foreman_trend_preview.html"}
)) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$($pair.Port)$($pair.Path)" -TimeoutSec 6
        Write-Output "  $($pair.Name): HTTP $($r.StatusCode) $($r.RawContentLength)B"
    } catch {
        Write-Output "  $($pair.Name): FAIL - $_"
    }
}

Write-Output "=== DONE ==="
Write-Output "Heat Dashboard : http://10.30.220.12:8891/"
Write-Output "Foreman Trend  : http://10.30.220.12:8892/foreman_trend_preview.html?ws_port=8768"
if ($needsUpload) {
    Write-Output "ACTION REQUIRED: Upload missing frontend files to $srcFE"
}
