$ErrorActionPreference = 'Stop'
Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'pspace_history.py' -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\backups\\' } |
  Select-Object -First 20 -ExpandProperty FullName
