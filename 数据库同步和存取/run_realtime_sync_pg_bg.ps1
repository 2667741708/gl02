param(
    [int]$PollSeconds = 30,
    [int]$LookbackMinutes = 10,
    [int]$BatchSize = 115,
    [ValidateSet("raw", "processed")]
    [string]$SourceMode = "raw",
    [int]$SourceIntervalSeconds = 5,
    [ValidateSet("sample", "last", "first", "average", "median")]
    [string]$SourceAggregate = "average",
    [int]$RawMaxValues = 20000,
    [switch]$ValidateOnly
)
$ErrorActionPreference = "Continue"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This realtime synchronization runner requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$ConfigPath = Join-Path $ScriptRoot "config\sync_config.json"
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Missing realtime sync configuration: $ConfigPath"
}
$LogDir = Join-Path $ScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$SharedLockDir = Join-Path $ProjectRoot 'logs'
New-Item -ItemType Directory -Force -Path $SharedLockDir | Out-Null
$LockPath = Join-Path $SharedLockDir 'realtime_sync_pg.lock'
$LockStream = $null
try {
    $LockStream = [System.IO.File]::Open(
        $LockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
}
catch {
    Write-Host 'another realtime sync wrapper already owns the lock; exiting'
    exit 0
}

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "PSPACE_SDK_ROOT") {
    $value = [Environment]::GetEnvironmentVariable($name, "Machine")
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($name, "User")
    }
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $env:GL02_PGHOST) { $env:GL02_PGHOST = "127.0.0.1" }
if (-not $env:GL02_PGPORT) { $env:GL02_PGPORT = "5432" }
if (-not $env:GL02_PGDATABASE) { $env:GL02_PGDATABASE = "bf_trend" }
if (-not $env:PSPACE_SERVER) { $env:PSPACE_SERVER = "10.22.181.243" }
if (-not $env:PSPACE_PORT) { $env:PSPACE_PORT = "8889" }

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
if (-not $Python) {
    $Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "User")
}
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}
$SyncEntry = Join-Path $ScriptRoot "src\sync_from_243_pg.py"
if ($ValidateOnly) {
    if (-not (Test-Path -LiteralPath $SyncEntry -PathType Leaf)) {
        throw "Realtime synchronization entry is unavailable: $SyncEntry"
    }
    [ordered]@{
        schema = 'ops.realtime-sync-runner.validate-only.v1'
        ok = $true
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        python = $Python
        entry = $SyncEntry
        config = $ConfigPath
    } | ConvertTo-Json -Depth 4
    exit 0
}
$LogPath = Join-Path $LogDir ("continuous_sync_pg_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

try {
while ($true) {
    $End = Get-Date
    $End = Get-Date -Date $End -Format "yyyy-MM-dd HH:mm:00"
    $Start = (Get-Date -Date $End).AddMinutes(-1 * [Math]::Max(3, $LookbackMinutes))
    $Start = Get-Date -Date $Start -Format "yyyy-MM-dd HH:mm:00"

    $line = "{0} sync_once start={1} end={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Start, $End
    $line | Tee-Object -FilePath $LogPath -Append

    & $Python $SyncEntry `
        --config $ConfigPath `
        --start-time $Start `
        --end-time $End `
        --chunk-hours 0.2 `
        --batch-size $BatchSize `
        --max-workers 1 `
        --retries 3 `
        --retry-sleep 8 `
        --source-mode $SourceMode `
        --source-interval-seconds $SourceIntervalSeconds `
        --source-aggregate $SourceAggregate `
        --raw-max-values $RawMaxValues `
        --target-aggregate PS_RAW_AVERAGE `
        --target-interval-seconds 60 `
        --persist-raw-5s `
        --raw-retention-days 30 `
        --skip-schema `
        *>&1 | Tee-Object -FilePath $LogPath -Append

    Start-Sleep -Seconds ([Math]::Max(30, $PollSeconds))
}
}
finally {
    if ($LockStream) {
        $LockStream.Dispose()
    }
    Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
}
