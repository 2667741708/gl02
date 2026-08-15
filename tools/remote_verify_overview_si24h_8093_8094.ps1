$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Frontend = Join-Path $Root '高炉前端数据'
$Page8093 = Join-Path $Frontend 'frontend_dashboard_v3.server.html'
$Page8094 = Join-Path $Frontend 'frontend_dashboard_v3.8094_preview.server.html'
$Main = Join-Path $Frontend 'assets\build\dashboard-main-DaGlW2vU.js'
function Get-Pid([int]$Port) { $item = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($item) { [int]$item.OwningProcess } else { $null } }
$Http8093 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?si24h_verify=$([DateTimeOffset]::Now.ToUnixTimeSeconds())#overview" -TimeoutSec 20
$Http8094 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?si24h_verify=$([DateTimeOffset]::Now.ToUnixTimeSeconds())#overview" -TimeoutSec 20
$Api8093 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/si-v20/hourly-table?limit=24' -TimeoutSec 30
$Api8094 = Invoke-RestMethod -Uri 'http://127.0.0.1:8094/api/si-v20/hourly-table?limit=24' -TimeoutSec 30
$MainText = [IO.File]::ReadAllText($Main, [Text.Encoding]::UTF8)
$Page8094Text = [IO.File]::ReadAllText($Page8094, [Text.Encoding]::UTF8)
$Backup = Get-ChildItem -LiteralPath (Join-Path $Root 'backups\overview_si24h_20260811') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$Ports = [ordered]@{}
foreach ($Port in @(8093,8094,8768,8770,5432,11434)) { $Ports[[string]$Port] = Get-Pid $Port }
[ordered]@{
    ok = ($Http8093.StatusCode -eq 200 -and $Http8094.StatusCode -eq 200 -and $Api8093.ok -and $Api8094.ok -and $MainText.Contains('hourly-table?limit=24') -and $MainText.Contains('每小时Si预测') -and $Page8094Text.Contains('REQ-8093-OVERVIEW-SI24H-20260811'))
    powershell = $PSVersionTable.PSVersion.ToString()
    http = [ordered]@{'8093'=[int]$Http8093.StatusCode;'8094'=[int]$Http8094.StatusCode}
    api = [ordered]@{'8093_count'=$Api8093.count;'8094_count'=$Api8094.count;'8093_schema'=$Api8093.schema;'8094_schema'=$Api8094.schema}
    contracts = [ordered]@{'8093_bundle'=($MainText.Contains('hourly-table?limit=24') -and $MainText.Contains('每小时Si预测') -and $MainText.Contains('炉次：'));'8094_page'=($Page8094Text.Contains('REQ-8093-OVERVIEW-SI24H-20260811') -and $Page8094Text.Contains('param.data?.meltno'))}
    hashes = [ordered]@{'8093'=(Get-FileHash -LiteralPath $Page8093 -Algorithm SHA256).Hash;'8094'=(Get-FileHash -LiteralPath $Page8094 -Algorithm SHA256).Hash;'main'=(Get-FileHash -LiteralPath $Main -Algorithm SHA256).Hash}
    ports = $Ports
    backup = if ($Backup) { $Backup.FullName } else { $null }
} | ConvertTo-Json -Depth 8
