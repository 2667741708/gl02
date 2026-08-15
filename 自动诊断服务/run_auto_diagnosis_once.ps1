[CmdletBinding()]
param(
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Continue"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This automatic diagnosis runner requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogDir = Join-Path $ScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

foreach ($name in "GL02_PGHOST", "GL02_PGPORT", "GL02_PGDATABASE", "GL02_PGUSER", "GL02_PGPASSWORD", "PSPACE_SERVER", "PSPACE_PORT", "PSPACE_USER", "PSPACE_PASSWORD", "OLLAMA_BASE_URL", "BF_LLM_MODEL") {
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
if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://10.30.220.12:11434" }
if (-not $env:BF_LLM_MODEL) { $env:BF_LLM_MODEL = "chiqiong-blast-furnace:latest" }

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Python = [Environment]::GetEnvironmentVariable("PYTHON_EXE", "Machine")
if (-not $Python) {
    $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = "python"
}

$AutoGuardPath = Join-Path $ScriptRoot "auto_guard_once.py"
if ($ValidateOnly) {
    if (-not (Test-Path -LiteralPath $AutoGuardPath -PathType Leaf)) {
        throw "Automatic diagnosis entry is unavailable: $AutoGuardPath"
    }
    [ordered]@{
        schema = 'ops.auto-diagnosis-runner.validate-only.v1'
        ok = $true
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        python = $Python
        entry = $AutoGuardPath
    } | ConvertTo-Json -Depth 4
    exit 0
}

$LogPath = Join-Path $LogDir ("auto_guard_once_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    $message = "Missing GL02_PGUSER/GL02_PGPASSWORD. Set machine-level PostgreSQL credentials before installing the scheduled task."
    $message | Tee-Object -FilePath $LogPath -Append
    exit 2
}

& $Python -X utf8 $AutoGuardPath `
    --since-hours 24 `
    --max-diagnosis-points 288 `
    --with-llm `
    --export-docx `
    --doctor `
    *>&1 | Tee-Object -FilePath $LogPath -Append

exit $LASTEXITCODE
