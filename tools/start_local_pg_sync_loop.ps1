param(
    [int]$IntervalSeconds = 30,
    [int]$BatchSize = 10000,
    [int]$LocalTunnelPort = 56432
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Logs = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

$PythonExe = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = "python"
}

if (-not $env:GL02_LOCAL_PGHOST) { $env:GL02_LOCAL_PGHOST = "127.0.0.1" }
if (-not $env:GL02_LOCAL_PGPORT) { $env:GL02_LOCAL_PGPORT = "15432" }
if (-not $env:GL02_LOCAL_PGDATABASE) { $env:GL02_LOCAL_PGDATABASE = "bf_trend" }
if (-not $env:GL02_LOCAL_PGUSER) { $env:GL02_LOCAL_PGUSER = "gl02_sync" }
if (-not $env:GL02_LOCAL_PGPASSWORD) { $env:GL02_LOCAL_PGPASSWORD = "gl02_local_sync" }

$SyncScript = Join-Path $Root "tools\sync_22012_pg_to_local.py"
if (-not (Test-Path -LiteralPath $SyncScript)) {
    throw "Missing sync script: $SyncScript"
}

$LogPath = Join-Path $Logs "local_pg_sync_loop.jsonl"
while ($true) {
    $started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        @{event="sync_start"; started_at=$started} | ConvertTo-Json -Compress | Add-Content -Encoding UTF8 -LiteralPath $LogPath
        & $PythonExe $SyncScript --batch-size $BatchSize --local-tunnel-port $LocalTunnelPort 2>&1 | Add-Content -Encoding UTF8 -LiteralPath $LogPath
        @{event="sync_finish"; finished_at=(Get-Date -Format "yyyy-MM-dd HH:mm:ss"); status="ok"} | ConvertTo-Json -Compress | Add-Content -Encoding UTF8 -LiteralPath $LogPath
    } catch {
        @{event="sync_error"; finished_at=(Get-Date -Format "yyyy-MM-dd HH:mm:ss"); error=$_.Exception.Message} | ConvertTo-Json -Compress | Add-Content -Encoding UTF8 -LiteralPath $LogPath
    }
    Start-Sleep -Seconds ([Math]::Max(30, $IntervalSeconds))
}
