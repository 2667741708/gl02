$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$service8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
$service8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
$port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
$port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
$pythonVersion = (& 'C:\Program Files\Python311\python.exe' --version 2>&1 | Out-String).Trim()

[pscustomobject]@{
  Service8093 = $service8093
  Service8768 = $service8768
  Port8093 = $port8093
  Port8768 = $port8768
  Python = $pythonVersion
} | ConvertTo-Json -Compress
