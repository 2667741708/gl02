$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewWs8768'" |
    Select-Object Name, State, StartMode, PathName |
    ConvertTo-Json
