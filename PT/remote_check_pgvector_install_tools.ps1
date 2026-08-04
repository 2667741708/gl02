$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

foreach ($cmd in @("winget","choco","scoop","curl","tar","git","nmake","cl")) {
    Write-Host "=== where $cmd ==="
    where.exe $cmd 2>&1
}

Write-Host "=== github pgvector latest ==="
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $content = (Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/pgvector/pgvector/releases/latest" -TimeoutSec 30).Content
    if ($content.Length -gt 1200) { $content.Substring(0,1200) } else { $content }
} catch {
    "github_error=" + $_.Exception.Message
}
