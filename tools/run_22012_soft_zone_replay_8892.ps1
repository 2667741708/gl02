$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This entrypoint requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python = 'C:\Program Files\Python311\python.exe'
$Server = Join-Path $ProjectRoot 'tools\soft_zone_replay_server.py'
$StaticDir = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay'
$DbConfig = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$LogDir = Join-Path $ProjectRoot 'logs'
$LogFile = Join-Path $LogDir 'soft_zone_replay_8892.log'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python runtime missing: $Python"
}
if (-not (Test-Path -LiteralPath $Server -PathType Leaf)) {
    throw "Replay server missing: $Server"
}
if (-not (Test-Path -LiteralPath $StaticDir -PathType Container)) {
    throw "Replay static directory missing: $StaticDir"
}
if (-not (Test-Path -LiteralPath $DbConfig -PathType Leaf)) {
    throw "Read-only database config missing: $DbConfig"
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

& $Python -u $Server `
    --host '0.0.0.0' `
    --port 8892 `
    --static-dir $StaticDir `
    --db-config $DbConfig `
    --log-file $LogFile `
    --log-level 'INFO'

exit $LASTEXITCODE
