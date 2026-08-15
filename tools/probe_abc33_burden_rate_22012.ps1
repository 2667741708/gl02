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
$SessionScript = Join-Path $PSScriptRoot 'remote_22012_session.py'
$ProbeScript = Join-Path $PSScriptRoot 'remote_probe_abc33_burden_rate_deploy.ps1'
$env:PYTHONPATH = Join-Path $ProjectRoot '.tmp_pylibs'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'

& $PythonPath $SessionScript ensure --allow-agents-password --workdir $RemoteRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Persistent SSH preflight failed.'
}

& $PythonPath $SessionScript run -- --no-profile --timeout 120 --workdir $RemoteRoot --script $ProbeScript
if ($LASTEXITCODE -ne 0) {
    throw 'Remote ABC33 burden-rate deployment probe failed.'
}
