$ErrorActionPreference='Stop'
$sync=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_from_243_pg.py' -File -ErrorAction SilentlyContinue|Select-Object -ExpandProperty FullName
$config=Get-ChildItem -LiteralPath 'F:\' -Recurse -Filter 'sync_config.json' -File -ErrorAction SilentlyContinue|Select-Object -ExpandProperty FullName
[pscustomobject]@{sync=@($sync);config=@($config)}|ConvertTo-Json -Depth 4
