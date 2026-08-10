$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891"
$taskName = "StandaloneHeatDashboard8891"
$taskPath = "\BlastFurnaceServices\"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = "$root\backups\heat_dashboard_fix_$stamp"

Write-Output "=== Heat Dashboard Fix Deployment $stamp ==="

# 1. Backup existing files
Write-Output "[1/5] Backing up existing files..."
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
foreach ($file in @("db_dashboard\heat_service.py", "db_dashboard\external_sources.py")) {
    $src = Join-Path $root $file
    if (Test-Path -LiteralPath $src) {
        $dst = Join-Path $backupDir $file
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
        Write-Output "  backed up: $file"
    }
}

# 2. Apply fixes to heat_service.py
Write-Output "[2/5] Patching heat_service.py (imes_ops_params credential fallback)..."
$heatService = Join-Path $root "db_dashboard\heat_service.py"
$content = Get-Content -LiteralPath $heatService -Raw -Encoding UTF8

# Fix 1: imes_ops_params credential fallback (IMES_OPS_DB_* -> IMES_DB_*)
$oldCredCheck = @'
    file_values = _credential_values()
    user = _setting("IMES_OPS_DB_USER", file_values)
    password = _setting("IMES_OPS_DB_PASSWORD", file_values)
    if not user or not password:
        raise RuntimeError("缺少 IMES 生产作业表只读账号配置")
'@
$newCredCheck = @'
    file_values = _credential_values()
    user = (
        os.getenv("IMES_OPS_DB_USER")
        or file_values.get("IMES_OPS_DB_USER")
        or file_values.get("IMES_DB_USER")
    )
    password = (
        os.getenv("IMES_OPS_DB_PASSWORD")
        or file_values.get("IMES_OPS_DB_PASSWORD")
        or file_values.get("IMES_DB_PASSWORD")
    )
    if not user or not password:
        raise RuntimeError("缺少 IMES 生产作业表只读账号配置")
'@

if ($content -match [regex]::Escape($oldCredCheck)) {
    $content = $content -replace [regex]::Escape($oldCredCheck), $newCredCheck
    Write-Output "  [OK] credential fallback applied"
} else {
    Write-Output "  [SKIP] credential fallback already applied or pattern changed"
}

# Fix 2: imes_ops_params host/port fallback
$oldHost = @'
    return {
        "host": _setting(
            "IMES_OPS_DB_HOST",
            file_values,
            "127.0.0.1",
        ),
        "port": int(_setting(
            "IMES_OPS_DB_PORT",
            file_values,
            "15433",
        )),
        "dbname": _setting(
            "IMES_OPS_DB_NAME",
            file_values,
            "vastbase",
        ),
        "user": user,
        "password": password,
        "connect_timeout": int(
            _setting("IMES_DB_CONNECT_TIMEOUT_SECONDS", file_values, "3")
        ),
        "options": "-c default_transaction_read_only=on -c statement_timeout=3500",
    }
'@
$newHost = @'
    return {
        "host": _setting(
            "IMES_OPS_DB_HOST",
            file_values,
            file_values.get("IMES_DB_HOST", "127.0.0.1"),
        ),
        "port": int(_setting(
            "IMES_OPS_DB_PORT",
            file_values,
            file_values.get("IMES_DB_PORT", "15433"),
        )),
        "dbname": _setting(
            "IMES_OPS_DB_NAME",
            file_values,
            file_values.get("IMES_DB_NAME", "vastbase"),
        ),
        "user": user,
        "password": password,
        "connect_timeout": 2,
        "options": "-c default_transaction_read_only=on -c statement_timeout=2000",
        "_max_attempts": 1,
    }
'@

if ($content -match [regex]::Escape($oldHost)) {
    $content = $content -replace [regex]::Escape($oldHost), $newHost
    Write-Output "  [OK] host/port fallback + fast-fail applied"
} else {
    Write-Output "  [SKIP] host/port fallback already applied or pattern changed"
}

# Fix 3: _vastbase_connect retry support
$oldRetry = 'def _vastbase_connect(params: dict[str, Any]):
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return psycopg.connect(**params, row_factory=dict_row)
        except psycopg.OperationalError as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))'
$newRetry = 'def _vastbase_connect(params: dict[str, Any]):
    last_error: Exception | None = None
    max_attempts = params.pop("_max_attempts", 3)
    for attempt in range(max_attempts):
        try:
            return psycopg.connect(**params, row_factory=dict_row)
        except psycopg.OperationalError as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(0.5 * (attempt + 1))'

if ($content -match [regex]::Escape($oldRetry)) {
    $content = $content -replace [regex]::Escape($oldRetry), $newRetry
    Write-Output "  [OK] retry support applied"
} else {
    Write-Output "  [SKIP] retry support already applied or pattern changed"
}

[IO.File]::WriteAllText($heatService, $content, [Text.UTF8Encoding]::new($false))

# 3. Patch external_sources.py catalog check
Write-Output "[3/5] Patching external_sources.py (catalog credential check)..."
$extSources = Join-Path $root "db_dashboard\external_sources.py"
$extContent = Get-Content -LiteralPath $extSources -Raw -Encoding UTF8

$oldExtCheck = '"vastbase_operations": bool(
                os.getenv("IMES_OPS_DB_PASSWORD")
                or _load_env_file(EXTERNAL_ENV).get("IMES_OPS_DB_PASSWORD")
            ),'
$newExtCheck = '"vastbase_operations": bool(
                os.getenv("IMES_OPS_DB_PASSWORD")
                or _load_env_file(EXTERNAL_ENV).get("IMES_OPS_DB_PASSWORD")
                or _load_env_file(LEGACY_IMES_ENV).get("IMES_DB_PASSWORD")
            ),'

if ($extContent -match [regex]::Escape($oldExtCheck)) {
    $extContent = $extContent -replace [regex]::Escape($oldExtCheck), $newExtCheck
    Write-Output "  [OK] catalog ops credential check patched"
} else {
    Write-Output "  [SKIP] catalog check already patched or pattern changed"
}

[IO.File]::WriteAllText($extSources, $extContent, [Text.UTF8Encoding]::new($false))

# 4. Restart the service
Write-Output "[4/5] Restarting dashboard service..."
$oldProcesses = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$root*db_dashboard*server.py*" }
foreach ($proc in $oldProcesses) {
    Stop-Process -Id ([int]$proc.ProcessId) -Force -ErrorAction SilentlyContinue
    Write-Output "  stopped python PID $($proc.ProcessId)"
}
Start-Sleep -Seconds 2

# Restart via scheduled task
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -ne 'Running') {
        Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        Write-Output "  started scheduled task"
    } else {
        Write-Output "  task already running"
    }
} else {
    Write-Output "  WARNING: scheduled task not found, starting manually..."
    $runner = Join-Path $root "run_22012_heat_dashboard_8891.ps1"
    if (Test-Path -LiteralPath $runner) {
        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner) -WindowStyle Hidden -PassThru
        Write-Output "  started manually PID $($proc.Id)"
    }
}

# 5. Verify
Write-Output "[5/5] Verifying..."
Start-Sleep -Seconds 4
$listener = Get-NetTCPConnection -State Listen -LocalPort 8891 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Output "  [OK] Port 8891 listening (PID $($listener.OwningProcess))"
} else {
    Write-Output "  [WARN] Port 8891 not listening yet"
}

try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8891/api/overview" -TimeoutSec 5
    Write-Output "  [OK] HTTP 200, sensor rows: $(($resp.Content | ConvertFrom-Json).sensor.rows)"
} catch {
    Write-Output "  [WARN] HTTP check failed: $_"
}

# Check scheduled task persistence
$taskState = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
if ($taskState) {
    $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Write-Output "  Task: $($taskState.State) | LastRun: $($info.LastRunTime) | Triggers: $($taskState.Triggers.TriggerType -join ',')"
}

# Verify firewall
$fw = Get-NetFirewallRule -Name "BlastFurnaceStandaloneHeatDashboard8891" -ErrorAction SilentlyContinue
Write-Output "  Firewall rule: $(if($fw){'present'}else{'MISSING'})"

Write-Output "=== Deployment Complete ==="
Write-Output "Backup: $backupDir"
