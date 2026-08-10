$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$events = Get-WinEvent -FilterHashtable @{ LogName = "Microsoft-Windows-TaskScheduler/Operational"; StartTime = (Get-Date).AddHours(-3) } -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -like "*V4PreviewWs8769*" } |
    Select-Object -First 30 TimeCreated, Id, LevelDisplayName, Message
$events | ConvertTo-Json -Depth 4
