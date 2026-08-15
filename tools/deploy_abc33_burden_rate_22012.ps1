[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$PythonPath = 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
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
$RemoteSession = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_abc33_burden_rate_8093.ps1'
$RemoteRestart8768 = Join-Path $Root 'tools\remote_restart_abc33_burden_rate_8768.ps1'
$LocalTests = Join-Path $Root 'tools\test_abc33_burden_rate_local.ps1'
$PythonLibs = Join-Path $Root '.tmp_pylibs'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_burden_rate_20260810_v1'
$Uploads = @(
    "$(Join-Path $Root '自动诊断服务\abc_burden_rate.py')=$Stage\abc_burden_rate.py",
    "$(Join-Path $Root '自动诊断服务\abc_factor_audit.py')=$Stage\abc_factor_audit.py",
    "$(Join-Path $Root '自动诊断服务\abc_feature_builder.py')=$Stage\abc_feature_builder.py",
    "$(Join-Path $Root '自动诊断服务\abc_public_review.py')=$Stage\abc_public_review.py",
    "$(Join-Path $Root '自动诊断服务\abc_rule_catalog.py')=$Stage\abc_rule_catalog.py",
    "$(Join-Path $Root '自动诊断服务\abc_rule_engine.py')=$Stage\abc_rule_engine.py",
    "$(Join-Path $Root '自动诊断服务\config\abc_furnace_rules.v1.json')=$Stage\abc_furnace_rules.v1.json",
    "$(Join-Path $Root '自动诊断服务\diagnosis_scheduler.py')=$Stage\diagnosis_scheduler.py",
    "$(Join-Path $Root '自动诊断服务\local_pg_ws_bridge.py')=$Stage\local_pg_ws_bridge.py"
)

foreach ($Path in @($RemoteSession, $RemoteDeploy, $RemoteRestart8768, $LocalTests) + ($Uploads | ForEach-Object { ($_ -split '=', 2)[0] })) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required local file missing: $Path" }
}

& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoLogo -NoProfile -NonInteractive -File $LocalTests -PythonPath $PythonPath
if ($LASTEXITCODE -ne 0) { throw 'Local ABC33 burden-rate gate failed; production was not changed.' }

$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $PythonLibs
try {
    & $PythonPath $RemoteSession ensure --allow-agents-password --workdir $RemoteRoot
    if ($LASTEXITCODE -ne 0) { throw 'Persistent 220.12 SSH session could not be ensured.' }

    $UploadArguments = @($RemoteSession, 'run', '--', '--no-profile', '--timeout', '120', '--workdir', $RemoteRoot, '--upload-only')
    foreach ($Upload in $Uploads) { $UploadArguments += @('--upload', $Upload) }
    & $PythonPath @UploadArguments
    if ($LASTEXITCODE -ne 0) { throw 'ABC33 burden-rate staging failed; production was not changed.' }

    & $PythonPath $RemoteSession run -- --no-profile --timeout 360 --workdir $RemoteRoot --script $RemoteDeploy
    if ($LASTEXITCODE -ne 0) { throw '8093 guarded deployment failed; inspect structured rollback evidence.' }

    & $PythonPath $RemoteSession run -- --no-profile --timeout 300 --workdir $RemoteRoot --script $RemoteRestart8768
    if ($LASTEXITCODE -ne 0) { throw '8768 controlled restart or WebSocket verification failed.' }

    & $PythonPath $RemoteSession status
    if ($LASTEXITCODE -ne 0) { throw 'Deployment completed but persistent SSH session health could not be proven.' }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
