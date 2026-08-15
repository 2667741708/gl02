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
$TargetHtml = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
$TargetBundle = Join-Path $Root '高炉前端数据\assets\build\dashboard-main-CcxwpZA4.js'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\8093_core_portal_baseline_20260811'
$StageHtml = Join-Path $StageRoot 'frontend_dashboard_v3.server.html'
$StageBundle = Join-Path $StageRoot 'dashboard-main-CcxwpZA4.js'

function Get-State {
    param([string]$Path)
    $Exists = Test-Path -LiteralPath $Path -PathType Leaf
    return [ordered]@{
        path = $Path
        exists = $Exists
        sha256 = if ($Exists) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash } else { $null }
        length = if ($Exists) { (Get-Item -LiteralPath $Path).Length } else { $null }
    }
}

$Http = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?probe=core-modal-baseline-stage' -TimeoutSec 20
$Body = [string]$Http.Content
[pscustomobject]@{
    ok = $true
    target_html = Get-State -Path $TargetHtml
    target_bundle = Get-State -Path $TargetBundle
    stage_html = Get-State -Path $StageHtml
    stage_bundle = Get-State -Path $StageBundle
    http = [ordered]@{
        status = [int]$Http.StatusCode
        production_marker = $Body.Contains('REQ-8093-FRONTEND-PERF-R1')
        browser_babel = $Body.Contains('babel.min.js')
        ccx_bundle = $Body.Contains('dashboard-main-CcxwpZA4.js')
        wbu_bundle = $Body.Contains('dashboard-main-WBUc0lNC.js')
    }
} | ConvertTo-Json -Depth 6
