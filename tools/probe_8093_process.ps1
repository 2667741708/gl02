$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Select-Object -First 30 ProcessId, ParentProcessId, CommandLine
Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalPort, OwningProcess
Get-ChildItem -LiteralPath '.\logs' -File |
    Where-Object { $_.Name -like '*proxy*' -or $_.Name -like '*8093*' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 10 Name, LastWriteTime
