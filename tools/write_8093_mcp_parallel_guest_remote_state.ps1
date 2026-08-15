[CmdletBinding()]
param(
    [string]$PreflightJson = '.tmp\8093-mcp-parallel-guest-20260813\preflight.json',
    [string]$OutputJson = '.tmp\8093-mcp-parallel-guest-20260813\remote-state.json'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PreflightJson = (Resolve-Path -LiteralPath (Join-Path $Root $PreflightJson)).Path
$OutputJson = Join-Path $Root $OutputJson
$Preflight = Get-Content -LiteralPath $PreflightJson -Raw -Encoding UTF8 | ConvertFrom-Json
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RelativeTargets = @(
    '高炉前端数据\frontend_dashboard_v3.server.html',
    '高炉前端数据\assets\abc-furnace-rules-production.js',
    '高炉前端数据\智能助手\backend\abc_score_explanation.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\schema\postgresql_assistant.sql',
    '高炉前端数据\智能助手\backend\schema\20260811_abc_contextual_assistant.sql'
)
$Targets = [ordered]@{}
foreach ($RelativeTarget in $RelativeTargets) {
    $RemoteProperty = @($Preflight.targets.PSObject.Properties | Where-Object Name -eq $RelativeTarget) |
        Select-Object -First 1
    if ($null -eq $RemoteProperty) { throw "Remote target inventory is missing $RelativeTarget." }
    $Target = $RemoteRoot.TrimEnd('\') + '\' + $RelativeTarget
    $Targets[$Target] = [ordered]@{
        exists = [bool]$RemoteProperty.Value.exists
        sha256 = [string]$RemoteProperty.Value.sha256
    }
}
$State = [ordered]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = 'REQ-8093-MCP-PARALLEL-5-AND-GUEST-DEPLOY-20260813'
    targets = $Targets
}
[IO.File]::WriteAllText($OutputJson, ($State | ConvertTo-Json -Depth 8), $Utf8NoBom)
$OutputJson
