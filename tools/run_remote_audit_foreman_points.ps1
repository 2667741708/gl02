$project = Get-Location
$root = Join-Path $project '数据库同步和存取'
$script = Join-Path $project 'tools\audit_foreman_points_db_before_deploy.py'
& 'C:\Program Files\Python311\python.exe' $script --root $root
exit $LASTEXITCODE
