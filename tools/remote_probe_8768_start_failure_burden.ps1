$ErrorActionPreference='Continue'
$Root='F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Service=Get-Service BFV4PreviewWs8768 -ErrorAction SilentlyContinue
$Config=Get-Content -LiteralPath (Join-Path $Root 'tools\service_configs\22012_BFV4PreviewWs8768.json') -Raw -Encoding UTF8|ConvertFrom-Json
$Logs=@(Get-ChildItem -LiteralPath (Join-Path $Root 'logs') -File -ErrorAction SilentlyContinue|Where-Object Name -Match '8768|ws'|Sort-Object LastWriteTime -Descending|Select-Object -First 4|ForEach-Object{[pscustomobject]@{path=$_.FullName;modified=$_.LastWriteTime;text=(Get-Content -LiteralPath $_.FullName -Tail 80 -Encoding UTF8 -ErrorAction SilentlyContinue)-join"`n"}})
$Events=@(Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=(Get-Date).AddMinutes(-15)} -ErrorAction SilentlyContinue|Where-Object Message -Match 'BFV4PreviewWs8768|local_pg_ws_bridge|python'|Select-Object -First 20 TimeCreated,Id,LevelDisplayName,Message)
[pscustomobject]@{service_status=$Service.Status.ToString();listener=(Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue|Select-Object -First 1 -ExpandProperty OwningProcess);config=$Config;logs=$Logs;events=$Events}|ConvertTo-Json -Depth 8
