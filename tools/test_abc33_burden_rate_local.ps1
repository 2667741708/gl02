[CmdletBinding()]
param(
    [string]$PythonPath = 'C:\Users\hmw20\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectRoot '.tmp_pylibs'
Set-Location -LiteralPath $ProjectRoot

$TestFiles = @(
    'tests/test_abc_burden_rate.py'
    'tests/test_abc_rule_engine.py'
    'tests/test_abc_public_review_labels.py'
    'tests/test_abc_common_factors.py'
    'tests/test_abc_replay.py'
    'tests/test_remote_22012_persistent_session.py'
)

& $PythonPath -m pytest -q @TestFiles
if ($LASTEXITCODE -ne 0) {
    throw 'ABC33 burden-rate local tests failed.'
}

$CompileFiles = @(
    '自动诊断服务/abc_burden_rate.py'
    '自动诊断服务/abc_factor_audit.py'
    '自动诊断服务/abc_feature_builder.py'
    '自动诊断服务/abc_public_review.py'
    '自动诊断服务/abc_rule_catalog.py'
    '自动诊断服务/abc_rule_engine.py'
    '自动诊断服务/diagnosis_scheduler.py'
    '自动诊断服务/local_pg_ws_bridge.py'
    'tools/remote_22012_session.py'
)

& $PythonPath -m py_compile @CompileFiles
if ($LASTEXITCODE -ne 0) {
    throw 'ABC33 burden-rate Python syntax validation failed.'
}

& $PythonPath -c "import sys; sys.path.insert(0, '自动诊断服务'); from abc_rule_engine import load_config, validate_config; validate_config(load_config()); print('abc_config_valid=true')"
if ($LASTEXITCODE -ne 0) {
    throw 'ABC33 configuration validation failed.'
}

$PowerShellFiles = @(
    'tools/start_remote_22012_session.ps1'
    'tools/stop_remote_22012_session.ps1'
    'tools/verify_remote_22012_session_reuse.ps1'
    'tools/probe_abc33_burden_rate_22012.ps1'
    'tools/remote_probe_abc33_burden_rate_deploy.ps1'
    'tools/deploy_abc33_burden_rate_22012.ps1'
    'tools/remote_guarded_deploy_abc33_burden_rate_8093.ps1'
    'tools/remote_restart_abc33_burden_rate_8768.ps1'
)
foreach ($Path in $PowerShellFiles) {
    $Tokens = $null
    $Errors = $null
    [Management.Automation.Language.Parser]::ParseFile(
        (Resolve-Path -LiteralPath $Path).Path,
        [ref]$Tokens,
        [ref]$Errors
    ) | Out-Null
    if ($Errors.Count -gt 0) {
        throw "PowerShell 7 parse validation failed for $Path`: $($Errors[0].Message)"
    }
}
Write-Output 'powershell7_scripts_valid=true'
