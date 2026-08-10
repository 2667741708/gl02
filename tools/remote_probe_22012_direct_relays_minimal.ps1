$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$config = "C:\Users\Administrator\Desktop\nginx-1.29.3\conf\nginx.conf"
$listeners = @(
    Get-NetTCPConnection -State Listen -LocalPort 18080,15433,18889,8093,8768,8094,8770 -ErrorAction SilentlyContinue |
        Sort-Object LocalPort |
        Select-Object LocalAddress, LocalPort, OwningProcess
)
$content = Get-Content -LiteralPath $config -Raw -Encoding UTF8
[ordered]@{
    checked_at = (Get-Date).ToString("s")
    nginx_marker = [bool]($content -match "OPS-22012-IMES-WEB-PROXY-20260805")
    nginx_sha256 = (Get-FileHash -LiteralPath $config -Algorithm SHA256).Hash
    listeners = $listeners
    portproxy = (& netsh.exe interface portproxy show v4tov4 2>&1 | Out-String).Trim()
    powershell_process_count = @(Get-Process -Name powershell -ErrorAction SilentlyContinue).Count
} | ConvertTo-Json -Depth 6
