$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$rows = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in @(8093, 8768, 8094, 8770) } |
    Select-Object LocalPort, OwningProcess
$rows | ConvertTo-Json
