$project = Get-Location
$root = Join-Path $project '数据库同步和存取'
$script = Join-Path $project 'tools\query_22012_water_points_latest.py'
& 'C:\Program Files\Python311\python.exe' $script --root $root
exit $LASTEXITCODE
