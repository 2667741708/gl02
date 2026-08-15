$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Repo
$env:PYTHONPATH = (Resolve-Path -LiteralPath '.tmp_pylibs').Path
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_burden_three_factor_20260811_v1'
$ArgsList = @(
    '.\tools\remote_22012_session.py', 'run', '--',
    '--allow-agents-password', '--no-profile', '--timeout', '180',
    '--workdir', 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    '--upload', "自动诊断服务\abc_burden_rate.py=$Stage\abc_burden_rate.py",
    '--upload', "自动诊断服务\abc_factor_audit.py=$Stage\abc_factor_audit.py",
    '--upload', "自动诊断服务\abc_feature_builder.py=$Stage\abc_feature_builder.py",
    '--upload', "自动诊断服务\abc_rule_catalog.py=$Stage\abc_rule_catalog.py",
    '--upload', "自动诊断服务\abc_term_semantics.py=$Stage\abc_term_semantics.py",
    '--script', '.\tools\remote_guarded_deploy_abc33_burden_rate_8093.ps1'
)
& python @ArgsList
if ($LASTEXITCODE -ne 0) { throw "8093 deployment failed with exit code $LASTEXITCODE" }
