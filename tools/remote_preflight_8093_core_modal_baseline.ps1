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

$RequirementId = 'BUG-8093-CORE-PORTAL-BASELINE-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$Targets = @(
    (Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'),
    (Join-Path $Root '高炉前端数据\assets\build\dashboard-main-CcxwpZA4.js')
)
$ProtectedPorts = @(8094, 8768, 8770, 5432, 8892, 11434)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$TargetState = [ordered]@{}
foreach ($Target in $Targets) {
    $Exists = Test-Path -LiteralPath $Target -PathType Leaf
    $TargetState[$Target] = [ordered]@{
        exists = $Exists
        sha256 = if ($Exists) { (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash } else { $null }
    }
}

$Listeners = [ordered]@{}
foreach ($Port in @(8093) + $ProtectedPorts) {
    $Listeners[[string]$Port] = Get-ListenerPid -Port $Port
}

[pscustomobject]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = $RequirementId
    targets = $TargetState
    service = [ordered]@{
        name = $ServiceName
        status = (Get-Service -Name $ServiceName -ErrorAction Stop).Status.ToString()
    }
    listeners = $Listeners
    powershell = [ordered]@{
        edition = $PSVersionTable.PSEdition
        version = $PSVersionTable.PSVersion.ToString()
    }
} | ConvertTo-Json -Depth 7
