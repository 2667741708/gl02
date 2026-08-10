$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    Write-Error "请先设置 GL02_PGUSER 和 GL02_PGPASSWORD。"
    exit 1
}

& $Python (Join-Path $ScriptRoot "src\init_pg.py")
