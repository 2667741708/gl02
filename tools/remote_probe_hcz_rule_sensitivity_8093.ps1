[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Targets = @(
    '炉况规则引擎\features\hcz_upward_expert_rule.py',
    '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\hcz_upward_rule.html',
    '高炉前端数据\assets\hcz-upward-rule.js',
    '高炉前端数据\assets\hcz-upward-rule.css'
)
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$Files = [ordered]@{}
foreach ($Relative in $Targets) {
    $Path = Join-Path $Root $Relative
    $Exists = Test-Path -LiteralPath $Path -PathType Leaf
    $Files[$Path] = [ordered]@{
        exists = $Exists
        sha256 = if ($Exists) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash } else { $null }
    }
}
$Protected = [ordered]@{}
foreach ($Port in $ProtectedPorts) { $Protected[[string]$Port] = Get-ListenerPid -Port $Port }
$Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/hcz_upward_rule.html?probe=$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())" -TimeoutSec 30
$Api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/hcz-upward-rule?probe=$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())" -TimeoutSec 120

[ordered]@{
    ok = $true
    requirement_id = 'REQ-HCZ-RULE-SENSITIVITY-20260811'
    powershell = [ordered]@{ edition = $PSVersionTable.PSEdition; version = $PSVersionTable.PSVersion.ToString() }
    service = [ordered]@{
        name = 'BFV4PreviewProxy8093'
        status = (Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop).Status.ToString()
        listener_pid = Get-ListenerPid -Port 8093
    }
    protected_pids = $Protected
    files = $Files
    page = [ordered]@{
        status = [int]$Page.StatusCode
        has_rule_marker = $Page.Content.Contains('HCZ-UP-FOREMAN-001')
        has_sensitivity_marker = $Page.Content.Contains('REQ-HCZ-RULE-SENSITIVITY-20260811')
    }
    api = [ordered]@{
        ok = [bool]$Api.ok
        status = [string]$Api.status
        requirement_id = [string]$Api.requirement_id
        pressure_label = [string]$Api.metrics.blast_pressure.label
        gas_utilisation_delta = $Api.metrics.gas_utilisation.delta
        gas_utilisation_normalised = $Api.source.gas_utilisation_normalised
    }
    remote_write_performed = $false
    service_restart_performed = $false
} | ConvertTo-Json -Depth 8
