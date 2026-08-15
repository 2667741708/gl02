[CmdletBinding()]
param()

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
$ServiceName = 'BFV4PreviewProxy8093'
$Python = 'C:\Program Files\Python311\python.exe'
$Targets = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\bf-core-metrics-pspace-live-8093.js',
    '高炉前端数据\assets\bf3d-furnace-body-billboard-adapter.js',
    '高炉前端数据\assets\bf3d-physical-point-filter-8093.js',
    '高炉前端数据\assets\bf3d-surface-camera-guard-8093.js',
    '高炉前端数据\assets\bf-shared-runtime-scheduler.js',
    '高炉前端数据\assets\build\dashboard-main-v9ebK4cf.js',
    '高炉前端数据\assets\build\overview-route-loader-Bv2DvOlP.js',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\http_static_compression.py'
)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$FileState = [ordered]@{}
foreach ($Relative in $Targets) {
    $Path = Join-Path $Root $Relative
    $Exists = Test-Path -LiteralPath $Path -PathType Leaf
    $FileState[$Relative] = [ordered]@{
        exists = $Exists
        sha256 = if ($Exists) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash } else { $null }
        length = if ($Exists) { (Get-Item -LiteralPath $Path).Length } else { $null }
    }
}

$Ports = [ordered]@{}
foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 8892, 11434)) {
    $Ports[[string]$Port] = Get-ListenerPid -Port $Port
}
$Http = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?preflight=frontend-perf-r1' -TimeoutSec 20
$BrotliAvailable = (& $Python -c 'import importlib.util; print("yes" if importlib.util.find_spec("brotli") else "no")').Trim() -eq 'yes'

[pscustomobject]@{
    ok = $true
    schema = 'bf.8093.frontend-perf.preflight.v1'
    ps_edition = $PSVersionTable.PSEdition
    ps_version = $PSVersionTable.PSVersion.ToString()
    python = $Python
    python_version = (& $Python --version 2>&1 | Out-String).Trim()
    brotli_available = $BrotliAvailable
    service = (Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString()
    ports = $Ports
    http_8093 = [int]$Http.StatusCode
    files = $FileState
} | ConvertTo-Json -Depth 7
