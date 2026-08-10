$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if ($env:PYTHON_EXE) { $env:PYTHON_EXE } else { "python" }
$LogPath = Join-Path $ScriptRoot ("logs\imes_sync_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$SyncScript = Get-ChildItem -LiteralPath $ScriptRoot -Filter "*IMES*.py" |
    Where-Object { $_.Name -like "*IMES*.py" } |
    Select-Object -First 1

if (-not $SyncScript) {
    Write-Error "Cannot find IMES sync Python script in $ScriptRoot."
    exit 1
}

if (-not $env:GL02_PGUSER -or -not $env:GL02_PGPASSWORD) {
    Write-Error "请先设置 GL02_PGUSER 和 GL02_PGPASSWORD。"
    exit 1
}

if (-not $env:IMES_USERNAME -or -not $env:IMES_PASSWORD) {
    Write-Error "请先设置 IMES_USERNAME 和 IMES_PASSWORD，或在项目根目录放置 .env.imes.local。"
    exit 1
}

& $Python $SyncScript.FullName `
    --dataset imes_10_pages `
    --date (Get-Date -Format "yyyy-MM-dd") `
    --page-size 200 `
    *>&1 | Tee-Object -FilePath $LogPath
