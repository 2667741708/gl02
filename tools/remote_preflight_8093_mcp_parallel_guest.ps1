[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$OutputPath = 'C:\Users\Administrator\AppData\Local\Temp\8093_mcp_parallel_guest_preflight.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

function Get-ListenerPid([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$RelativeTargets = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\智能助手\backend\abc_score_explanation.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql',
    '高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql',
    'tools\service_configs\22012_BFV4PreviewProxy8093.json'
)
$Targets = [ordered]@{}
foreach ($Relative in $RelativeTargets) {
    $Path = Join-Path $Root $Relative
    $Targets[$Relative] = [ordered]@{
        exists = Test-Path -LiteralPath $Path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $Path -PathType Leaf) {
            (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        } else { $null }
    }
}

$Status = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 20
$GuestHttp = 0
$GuestMode = ''
try {
    $Guest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 20
    $GuestHttp = 200
    $GuestMode = [string]$Guest.access_mode
}
catch {
    if ($_.Exception.Response) { $GuestHttp = [int]$_.Exception.Response.StatusCode }
    else { throw }
}

$Result = [ordered]@{
    ok = $true
    schema = 'bf.8093-mcp-parallel-guest-preflight.v1'
    collected_at = (Get-Date).ToString('o')
    pwsh = $PSVersionTable.PSVersion.ToString()
    service = (Get-Service 'BFV4PreviewProxy8093').Status.ToString()
    listeners = [ordered]@{
        '8093' = Get-ListenerPid 8093
        '8094' = Get-ListenerPid 8094
        '8768' = Get-ListenerPid 8768
        '8770' = Get-ListenerPid 8770
        '5432' = Get-ListenerPid 5432
        '11434' = Get-ListenerPid 11434
    }
    targets = $Targets
    ollama_ok = [bool]$Status.ok
    current_qa_bootstrap_http = $GuestHttp
    current_access_mode = $GuestMode
    production_write_performed = $false
}
$OutputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
}
[IO.File]::WriteAllText($OutputPath, ($Result | ConvertTo-Json -Depth 7), $Utf8NoBom)
$Result | ConvertTo-Json -Depth 7
