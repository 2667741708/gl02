$ErrorActionPreference = 'Stop'
Get-ChildItem -Path 'F:\' -Filter 'manage_22012_managed_services.ps1' -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 20 -ExpandProperty FullName
