param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$RemoteExec = Join-Path $Root 'tools\remote_22012_exec.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_hcz_expert_label_8892.ps1'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_label_20260810'

$Uploads = @(
    "$(Join-Path $Root 'tools\soft_zone_replay_server.py')=$StageRoot\soft_zone_replay_server.py",
    "$(Join-Path $Root 'tools\run_22012_soft_zone_replay_8892.ps1')=$StageRoot\run_22012_soft_zone_replay_8892.ps1",
    "$(Join-Path $Root '高炉前端数据\soft_zone_replay\soft-zone-replay.js')=$StageRoot\soft-zone-replay.js",
    "$(Join-Path $Root '高炉前端数据\soft_zone_replay\hcz-labeling.html')=$StageRoot\hcz-labeling.html",
    "$(Join-Path $Root '高炉前端数据\soft_zone_replay\hcz-labeling.css')=$StageRoot\hcz-labeling.css",
    "$(Join-Path $Root '高炉前端数据\soft_zone_replay\hcz-labeling.js')=$StageRoot\hcz-labeling.js",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\hcz_expert_label.py')=$StageRoot\hcz_expert_label.py",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\schema\postgresql_hcz_expert_label.sql')=$StageRoot\postgresql_hcz_expert_label.sql"
)

foreach ($Path in @($RemoteExec, $RemoteDeploy) + ($Uploads | ForEach-Object { ($_ -split '=', 2)[0] })) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required local file missing: $Path"
    }
}

$Python = (Get-Command -Name python -ErrorAction Stop).Source
$StageArguments = @(
    $RemoteExec,
    '--allow-agents-password',
    '--no-profile',
    '--timeout', '60',
    '--workdir', $RemoteRoot,
    '--upload-only'
)
foreach ($Upload in $Uploads) {
    $StageArguments += @('--upload', $Upload)
}
& $Python @StageArguments
if ($LASTEXITCODE -ne 0) {
    throw 'HCZ labeling staging failed; production was not changed.'
}

& $Python $RemoteExec --allow-agents-password --no-profile --timeout 240 --workdir $RemoteRoot --script $RemoteDeploy
if ($LASTEXITCODE -ne 0) {
    throw 'HCZ labeling deployment failed; inspect the rollback evidence.'
}
