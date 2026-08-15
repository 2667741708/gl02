[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This preflight requires PowerShell 7 Core or later.'
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

$Targets = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\bf-abc33-assistant-dialog.js',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
)
$Hashes = [ordered]@{}
foreach ($RelativePath in $Targets) {
    $Path = Join-Path $Root $RelativePath
    $Hashes[$RelativePath] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$Latest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest' -TimeoutSec 20
$Rule = @($Latest.rules)[0]
$EvaluationId = if ($Rule.evaluation_id) { $Rule.evaluation_id } else { $Latest.evaluation_id }
$AnonymousStatus = 0
try {
    $Uri = "http://127.0.0.1:8093/api/furnace-rules/$($Rule.rule_id)/explanation-context?evaluation_id=$EvaluationId"
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20 | Out-Null
    $AnonymousStatus = 200
}
catch {
    if ($_.Exception.Response) { $AnonymousStatus = [int]$_.Exception.Response.StatusCode }
    else { throw }
}

[ordered]@{
    schema = 'bug.8093.abc33-advice-unavailable.preflight.v1'
    collected_at = (Get-Date).ToString('o')
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service 'BFV4PreviewProxy8093').Status.ToString()
        BFV4PreviewWs8768 = (Get-Service 'BFV4PreviewWs8768').Status.ToString()
    }
    listeners = [ordered]@{
        '8093' = Get-ListenerPid 8093
        '8094' = Get-ListenerPid 8094
        '8768' = Get-ListenerPid 8768
        '8770' = Get-ListenerPid 8770
        '5432' = Get-ListenerPid 5432
        '11434' = Get-ListenerPid 11434
    }
    target_hashes = $Hashes
    sample_rule_id = $Rule.rule_id
    sample_evaluation_id = $EvaluationId
    anonymous_explanation_http = $AnonymousStatus
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
