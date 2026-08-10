$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Get-WinEvent -FilterHashtable @{ LogName = "System"; ProviderName = "Service Control Manager"; StartTime = (Get-Date).AddHours(-2) } |
    Where-Object { $_.Message -like "*BFV4PreviewProxy8093*" -or $_.Message -like "*Blast Furnace V4 Preview Proxy 8093*" } |
    Select-Object -First 20 TimeCreated, Id, LevelDisplayName, Message |
    ConvertTo-Json -Depth 4
