param(
    [switch]$DryRun,
    [switch]$Restart,
    [switch]$SkipAssistant,
    [switch]$SkipFrontend,
    [switch]$SkipDiagnosis,
    [switch]$SkipRealtimeBridge,
    [switch]$SkipLocalSyncLoop,
    [int]$AssistantPort = 8092,
    [int]$FrontendPort = 8093,
    [int]$WsPort = 8767,
    [int]$LocalSyncIntervalSeconds = 30
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw "start_v3_full.ps1 只允许使用 PowerShell 7 Core；请运行 pwsh.exe -NoLogo -NoProfile -File .\start_v3_full.ps1"
}
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

Write-Host "[V3] Root: $Root"
Write-Host "[V3] PostgreSQL credentials are read from GL02_PGUSER/GL02_PGPASSWORD."

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

$UseExistingPgEnv = $env:BF_USE_EXISTING_PG_ENV -and $env:BF_USE_EXISTING_PG_ENV.ToString().ToLowerInvariant() -in @("1", "true", "yes")
if (-not $UseExistingPgEnv) {
    # Local full startup must use the local Docker PostgreSQL writer. The user-level
    # environment may point at the 220.12 read-only account, which cannot persist QA/RAG.
    $env:GL02_PGHOST = "127.0.0.1"
    $env:GL02_PGPORT = "15432"
    $env:GL02_PGDATABASE = "bf_trend"
    $env:GL02_PGUSER = "gl02_sync"
    $env:GL02_PGPASSWORD = "gl02_local_sync"
} else {
    if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
    if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "15432" }
    if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
    if (-not $env:GL02_PGUSER) { $env:GL02_PGUSER = "gl02_sync" }
    if (-not $env:GL02_PGPASSWORD) { $env:GL02_PGPASSWORD = "gl02_local_sync" }
}
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://10.30.220.12:11434" }
if (-not $env:BF_LLM_MODEL) { $env:BF_LLM_MODEL = "chiqiong-blast-furnace:latest" }
if (-not $env:BF_SKIP_ZERO_AUDIT) { $env:BF_SKIP_ZERO_AUDIT = "1" }

function Get-ListenerPids {
    param([int[]]$Ports)
    $connections = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $Ports -contains $_.LocalPort -and $_.OwningProcess }
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Get-ManagedProcessPids {
    param([string[]]$Patterns)
    if (-not $Patterns -or $Patterns.Count -eq 0) { return @() }
    $matches = Get-CimInstance Win32_Process | Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        $matched = $false
        foreach ($pattern in $Patterns) {
            if ($cmd -like "*$pattern*") {
                $matched = $true
                break
            }
        }
        return $matched
    }
    return @($matches | Select-Object -ExpandProperty ProcessId -Unique)
}

function Stop-Pids {
    param([int[]]$Pids)
    foreach ($pidValue in ($Pids | Sort-Object -Unique)) {
        if ($pidValue -and $pidValue -ne $PID) {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        }
    }
}

$ManagedPorts = @()
if (-not $SkipAssistant) { $ManagedPorts += $AssistantPort }
if (-not $SkipFrontend) { $ManagedPorts += $FrontendPort }
if (-not $SkipRealtimeBridge) { $ManagedPorts += $WsPort }

$ManagedPatterns = @()
if (-not $SkipDiagnosis) { $ManagedPatterns += "自动诊断服务\run_service.py" }
if (-not $SkipAssistant) {
    $ManagedPatterns += "智能助手\backend\run_local_8092.py"
    $ManagedPatterns += "智能助手\backend\ollama_proxy_server.py"
}
if (-not $SkipRealtimeBridge) { $ManagedPatterns += "自动诊断服务\local_pg_ws_bridge.py" }
if (-not $SkipFrontend) { $ManagedPatterns += "http.server $FrontendPort" }
if (-not $SkipLocalSyncLoop) { $ManagedPatterns += "tools\start_local_pg_sync_loop.ps1" }

if ($Restart) {
    $listenerPids = Get-ListenerPids -Ports $ManagedPorts
    $managedPids = Get-ManagedProcessPids -Patterns $ManagedPatterns
    $pidsToStop = @($listenerPids + $managedPids | Sort-Object -Unique)
    if ($pidsToStop.Count -gt 0) {
        Write-Host "[V3] Restart requested; stopping existing local service PIDs: $($pidsToStop -join ', ')"
        Stop-Pids -Pids $pidsToStop
        Start-Sleep -Seconds 2
    }
} else {
    $busyPids = @(Get-ListenerPids -Ports $ManagedPorts)
    $runningManagedPids = @(Get-ManagedProcessPids -Patterns $ManagedPatterns)
    if ($busyPids.Count -gt 0 -or $runningManagedPids.Count -gt 0) {
        $busyPorts = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $ManagedPorts -contains $_.LocalPort -and $_.OwningProcess } |
            Select-Object LocalAddress, LocalPort, OwningProcess
        $busyText = ($busyPorts | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort) pid=$($_.OwningProcess)" }) -join "; "
        throw "Local V3 services are already running or ports are occupied. $busyText Use -Restart to stop them first, or pass Skip* switches for services you do not want to manage."
    }
}

if (-not $SkipDiagnosis) {
    if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
        if ($DryRun) {
            Write-Warning "GL02_PGUSER/GL02_PGPASSWORD not set; skipping diagnosis dry-run that needs PostgreSQL."
            $SkipDiagnosis = $true
        } else {
            throw "GL02_PGUSER/GL02_PGPASSWORD not set. Refusing to start automatic diagnosis without PostgreSQL credentials."
        }
    }
}

if (-not $SkipDiagnosis) {
    $diag = Join-Path $Root "自动诊断服务\run_service.py"
    if (-not (Test-Path -LiteralPath $diag)) { throw "Missing $diag" }
    $args = @($diag)
    if ($env:BF_SKIP_ZERO_AUDIT.ToString().ToLowerInvariant() -in @("1", "true", "yes")) { $args += "--skip-zero-audit" }
    if ($DryRun) { $args += "--dry-run" }
    if ($DryRun) { $args += "--once" }
    Write-Host "[V3] Starting automatic diagnosis service..."
    if ($DryRun) {
        & $PythonExe @args 2>&1 | Tee-Object -FilePath (Join-Path $Logs "v3_auto_diagnosis_once.log")
    } else {
        Start-Process -FilePath $PythonExe `
            -ArgumentList $args `
            -WorkingDirectory $Root `
            -RedirectStandardOutput (Join-Path $Logs "v3_auto_diagnosis_service.out.log") `
            -RedirectStandardError (Join-Path $Logs "v3_auto_diagnosis_service.err.log") `
            -WindowStyle Hidden
    }
}

if (-not $SkipAssistant) {
    $assistant = Join-Path $Root "高炉前端数据\智能助手\backend\run_local_8092.py"
    if (Test-Path -LiteralPath $assistant) {
        Write-Host "[V3] Starting assistant backend on port $AssistantPort..."
        $env:BF_PROXY_PORT = [string]$AssistantPort
        if (-not $env:BF_ASSISTANT_PG_SCHEMA) { $env:BF_ASSISTANT_PG_SCHEMA = "bf_assistant" }
        if (-not $env:BF_MCP_DATA_SOURCE) { $env:BF_MCP_DATA_SOURCE = "hybrid" }
        Start-Process -FilePath $PythonExe `
            -ArgumentList @($assistant) `
            -WorkingDirectory (Split-Path -Parent $assistant) `
            -RedirectStandardOutput (Join-Path $Logs "assistant_8092.out.log") `
            -RedirectStandardError (Join-Path $Logs "assistant_8092.err.log") `
            -WindowStyle Hidden
    } else {
        Write-Warning "Assistant backend not found: $assistant"
    }
}

if (-not $SkipLocalSyncLoop) {
    $syncLoop = Join-Path $Root "tools\start_local_pg_sync_loop.ps1"
    if (Test-Path -LiteralPath $syncLoop) {
        Write-Host "[V3] Starting 220.12 -> local PostgreSQL sync loop every $LocalSyncIntervalSeconds seconds..."
        Start-Process -FilePath "pwsh.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $syncLoop, "-IntervalSeconds", "$LocalSyncIntervalSeconds") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput (Join-Path $Logs "local_pg_sync_loop.out.log") `
            -RedirectStandardError (Join-Path $Logs "local_pg_sync_loop.err.log") `
            -WindowStyle Hidden
    } else {
        Write-Warning "Local sync loop not found: $syncLoop"
    }
}

if (-not $SkipRealtimeBridge) {
    $wsBridge = Join-Path $Root "自动诊断服务\local_pg_ws_bridge.py"
    if (Test-Path -LiteralPath $wsBridge) {
        Write-Host "[V3] Starting PostgreSQL realtime WebSocket bridge on port $WsPort..."
        $env:BF_WS_HOST = "0.0.0.0"
        $env:BF_WS_PORT = [string]$WsPort
        $env:BF_WS_HISTORY_HOURS = if ($env:BF_WS_HISTORY_HOURS) { $env:BF_WS_HISTORY_HOURS } else { "8" }
        $env:BF_WS_TICK_SECONDS = if ($env:BF_WS_TICK_SECONDS) { $env:BF_WS_TICK_SECONDS } else { "30" }
        Start-Process -FilePath $PythonExe `
            -ArgumentList @($wsBridge) `
            -WorkingDirectory $Root `
            -RedirectStandardOutput (Join-Path $Logs "pg_ws_$WsPort.out.log") `
            -RedirectStandardError (Join-Path $Logs "pg_ws_$WsPort.err.log") `
            -WindowStyle Hidden
    } else {
        Write-Warning "PostgreSQL WebSocket bridge not found: $wsBridge"
    }
}

if (-not $SkipFrontend) {
    $frontendDir = Join-Path $Root "高炉前端数据"
    if (Test-Path -LiteralPath $frontendDir) {
        Write-Host "[V3] Starting frontend static server on port $FrontendPort..."
        Start-Process -FilePath $PythonExe `
            -ArgumentList @("-m", "http.server", "$FrontendPort") `
            -WorkingDirectory $frontendDir `
            -RedirectStandardOutput (Join-Path $Logs "frontend_$FrontendPort.out.log") `
            -RedirectStandardError (Join-Path $Logs "frontend_$FrontendPort.err.log") `
            -WindowStyle Hidden
        Write-Host "[V3] Frontend URL: http://127.0.0.1:$FrontendPort/frontend_dashboard_v3.server.html?ws_port=$WsPort"
    }
}

Write-Host "[V3] Startup command completed."
