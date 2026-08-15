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
$env:PYTHONPATH = Join-Path $ProjectRoot '.tmp_pylibs'
$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'

$FirstProbe = '[ordered]@{Edition=$PSVersionTable.PSEdition;Version=$PSVersionTable.PSVersion.ToString();RemotePid=$PID;Now=(Get-Date -Format o)} | ConvertTo-Json -Compress'
$SecondProbe = '[ordered]@{Service=(Get-Service -Name BFV4PreviewProxy8093).Status.ToString();Listening=[bool](Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue);Now=(Get-Date -Format o)} | ConvertTo-Json -Compress'

& $PythonPath $SessionScript run -- --no-profile --timeout 60 --workdir $RemoteRoot --command $FirstProbe
if ($LASTEXITCODE -ne 0) {
    throw 'The first persistent SSH probe failed.'
}

& $PythonPath $SessionScript run -- --no-profile --timeout 60 --workdir $RemoteRoot --command $SecondProbe
if ($LASTEXITCODE -ne 0) {
    throw 'The second persistent SSH probe failed.'
}

& $PythonPath $SessionScript status
if ($LASTEXITCODE -ne 0) {
    throw 'The persistent SSH status check failed.'
}
