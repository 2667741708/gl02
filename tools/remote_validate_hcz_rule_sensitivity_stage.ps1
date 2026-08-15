[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This validation requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-HCZ-RULE-SENSITIVITY-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_rule_sensitivity_20260811'
$PlanPath = Join-Path $StageRoot 'delta-plan.json'
$Python = 'C:\Program Files\Python311\python.exe'
$AllowedTargets = @(
    (Join-Path $Root '炉况规则引擎\features\hcz_upward_expert_rule.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py'),
    (Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'),
    (Join-Path $Root '高炉前端数据\hcz_upward_rule.html'),
    (Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.js'),
    (Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.css')
)

if (-not (Test-Path -LiteralPath $PlanPath -PathType Leaf)) { throw 'Staged delta plan is missing.' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Remote Python is missing.' }
$Plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Plan.schema -ne 'bf.deploy.delta-plan.v1' -or $Plan.requirement_id -ne $RequirementId) { throw 'Delta plan identity mismatch.' }

$Results = @()
$PythonStages = @()
foreach ($Change in @($Plan.changes)) {
    $Stage = [string]$Change.stage
    $Target = [IO.Path]::GetFullPath([string]$Change.target)
    if ($AllowedTargets -notcontains $Target) { throw "Target not allowlisted: $Target" }
    if (-not (Test-Path -LiteralPath $Stage -PathType Leaf)) { throw "Stage missing: $Stage" }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Target missing: $Target" }
    $StageHash = (Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash
    $TargetHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    $Baselines = @($Change.baseline_sha256 | ForEach-Object { [string]$_ })
    if ($StageHash -ne [string]$Change.desired_sha256) { throw "Staged hash mismatch: $Stage" }
    if ($Baselines -notcontains $TargetHash) { throw "Baseline mismatch: $Target" }
    $Text = Get-Content -LiteralPath $Stage -Raw -Encoding UTF8
    foreach ($Marker in @($Change.markers)) {
        if (-not $Text.Contains([string]$Marker)) { throw "Marker missing: $Marker in $Stage" }
    }
    if ($Stage.EndsWith('.py')) { $PythonStages += $Stage }
    $Results += [ordered]@{ target = $Target; staged_sha256 = $StageHash; baseline_sha256 = $TargetHash }
}

& $Python -m py_compile @PythonStages
if ($LASTEXITCODE -ne 0) { throw 'Staged Python syntax validation failed.' }

$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Available = $false
try {
    $Available = $Mutex.WaitOne(0)
}
finally {
    if ($Available) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}

[ordered]@{
    ok = $true
    requirement_id = $RequirementId
    change_count = $Results.Count
    mutex_available = $Available
    files = $Results
    remote_write_performed = $false
    service_restart_performed = $false
} | ConvertTo-Json -Depth 6
