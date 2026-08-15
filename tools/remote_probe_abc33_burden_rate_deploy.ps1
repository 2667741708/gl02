$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RelativeTargets = @(
    '自动诊断服务\abc_burden_rate.py'
    '自动诊断服务\abc_factor_audit.py'
    '自动诊断服务\abc_feature_builder.py'
    '自动诊断服务\abc_public_review.py'
    '自动诊断服务\abc_rule_catalog.py'
    '自动诊断服务\abc_rule_engine.py'
    '自动诊断服务\config\abc_furnace_rules.v1.json'
    '自动诊断服务\diagnosis_scheduler.py'
    '自动诊断服务\local_pg_ws_bridge.py'
)

$Files = foreach ($Relative in $RelativeTargets) {
    $Target = Join-Path $Root $Relative
    [ordered]@{
        relative = $Relative
        exists = Test-Path -LiteralPath $Target -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $Target -PathType Leaf) { (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash } else { $null }
    }
}

$Services = foreach ($Name in @('BFV4PreviewProxy8093', 'BFV4PreviewWs8768')) {
    $Service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    [ordered]@{
        name = $Name
        exists = [bool]$Service
        status = if ($Service) { $Service.Status.ToString() } else { $null }
    }
}

$Ports = [ordered]@{}
foreach ($Port in @(5432, 8093, 8094, 8768, 8770, 8892, 11434)) {
    $Listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    $Ports[[string]$Port] = if ($Listener) { [int]$Listener.OwningProcess } else { $null }
}

$Tasks = Get-ScheduledTask -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match 'Diagnosis|Baseline|ABC|Furnace' } |
    Select-Object TaskPath, TaskName, State

[ordered]@{
    ok = $true
    requirement_id = 'REQ-ABC33-HEAT-BATCH-RATE-CRITERION-20260810'
    powershell = $PSVersionTable.PSVersion.ToString()
    root = $Root
    files = @($Files)
    services = @($Services)
    ports = $Ports
    scheduled_tasks = @($Tasks)
} | ConvertTo-Json -Depth 8
