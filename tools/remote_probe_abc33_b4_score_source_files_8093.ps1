[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core or later is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Targets = @(
    '高炉前端数据\智能助手\backend\diagnosis_review.py',
    '高炉前端数据\智能助手\backend\diagnosis_model_review.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\assets\bf-diagnosis-review-local.js',
    '高炉前端数据\assets\bf-diagnosis-manual-score-local.js'
)
$Hashes = [ordered]@{}
foreach ($Relative in $Targets) {
    $Path = Join-Path $Root $Relative
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing production target: $Path" }
    $Hashes[$Relative] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}
$Ports = [ordered]@{}
foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 8892, 11434)) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $Ports[[string]$Port] = if ($Listener) { [int]$Listener.OwningProcess } else { $null }
}
[pscustomobject]@{
    schema = 'bf.8093.abc33-b4-score-source.files-probe.v1'
    ok = $true
    service_8093 = (Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop).Status.ToString()
    listener_pids = $Ports
    hashes = $Hashes
} | ConvertTo-Json -Depth 6 -Compress
