$ErrorActionPreference='Stop'
$root=Get-ChildItem -LiteralPath 'F:\' -Directory | Where-Object {$_.Name -match 'V4_8093_PREVIEW'} | Select-Object -First 1
if(-not $root){throw 'V4 root not found'}
Get-ChildItem -LiteralPath $root.FullName -Recurse -File -ErrorAction SilentlyContinue |
 Where-Object {$_.LastWriteTime -ge (Get-Date).AddHours(-3) -and ($_.Name -match 'sync|backfill|cooling|pspace' -or $_.DirectoryName -match 'logs')} |
 Sort-Object LastWriteTime -Descending |
 Select-Object -First 80 FullName,Length,LastWriteTime
