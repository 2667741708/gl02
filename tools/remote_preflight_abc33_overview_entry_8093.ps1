$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This preflight requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Targets = @(
    Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
    Join-Path $Root '高炉前端数据\assets\abc-furnace-rules-production.js'
)
$Ports = @(8093, 8094, 8768, 8770, 5432, 11434)
$Listeners = [ordered]@{}
foreach ($Port in $Ports) {
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $Listeners[[string]$Port] = if ($Row) { [int]$Row.OwningProcess } else { $null }
}
$Hashes = [ordered]@{}
foreach ($Target in $Targets) {
    $Hashes[$Target] = if (Test-Path -LiteralPath $Target) {
        (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    } else {
        $null
    }
}
$Service = Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop
$Http = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?cb=abc33-overview-preflight' -TimeoutSec 20
[ordered]@{
    ok = ($Service.Status -eq 'Running' -and [int]$Http.StatusCode -eq 200)
    requirement_id = 'BUG-8093-ABC33-OVERVIEW-ENTRY-20260811'
    powershell = $PSVersionTable.PSVersion.ToString()
    edition = $PSVersionTable.PSEdition
    service = $Service.Status.ToString()
    http_8093 = [int]$Http.StatusCode
    listeners = $Listeners
    hashes = $Hashes
} | ConvertTo-Json -Depth 6
