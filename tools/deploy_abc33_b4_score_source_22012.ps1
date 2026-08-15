[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$PythonPath = 'python'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core or later is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_abc33_b4_score_source_8093.ps1'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_b4_score_source_20260810_v2'
$Uploads = @(
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_review.py')=$Stage\diagnosis_review.py",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_model_review.py')=$Stage\diagnosis_model_review.py",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py')=$Stage\ollama_proxy_server.py",
    "$(Join-Path $Root '高炉前端数据\assets\bf-diagnosis-review-local.js')=$Stage\bf-diagnosis-review-local.js",
    "$(Join-Path $Root '高炉前端数据\assets\bf-diagnosis-manual-score-local.js')=$Stage\bf-diagnosis-manual-score-local.js"
)
foreach ($Path in @($Session, $RemoteDeploy) + ($Uploads | ForEach-Object { ($_ -split '=', 2)[0] })) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Required local file missing: $Path" }
}

$Pytest = (Get-Command -Name pytest -ErrorAction Stop).Source
& $Pytest -q (Join-Path $Root 'tests\test_diagnosis_review_api.py') (Join-Path $Root 'tests\test_diagnosis_review_contract.py') (Join-Path $Root 'tests\test_diagnosis_ai_analysis.py')
if ($LASTEXITCODE -ne 0) { throw 'Local score-source tests failed; production was not changed.' }

$PreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Resolve-Path -LiteralPath (Join-Path $Root '.tmp_pylibs')).Path
try {
    & $PythonPath $Session ensure --allow-agents-password --workdir $RemoteRoot
    if ($LASTEXITCODE -ne 0) { throw 'Persistent SSH session could not be ensured.' }
    $UploadArguments = @($Session, 'run', '--', '--no-profile', '--timeout', '120', '--workdir', $RemoteRoot, '--upload-only')
    foreach ($Upload in $Uploads) { $UploadArguments += @('--upload', $Upload) }
    & $PythonPath @UploadArguments
    if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed; production was not changed.' }
    & $PythonPath $Session run -- --no-profile --timeout 360 --workdir $RemoteRoot --script $RemoteDeploy
    if ($LASTEXITCODE -ne 0) { throw 'Guarded 8093 deployment failed; inspect structured rollback evidence.' }
    & $PythonPath $Session status
    if ($LASTEXITCODE -ne 0) { throw 'Deployment completed but persistent session health is unknown.' }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
