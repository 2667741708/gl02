[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = 'D:\ProgramData\anaconda3\python.exe'
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_answer_integrity_20260814'
$Arguments = @(
    $Session, 'run', '--', '--upload-only',
    '--upload', ".tmp\8093-body-temperature-answer-integrity-remote-review\ollama_proxy_server.remote.py=$Stage\ollama_proxy_server.py",
    '--upload', "高炉前端数据\智能助手\backend\mcp_host\domain_router.py=$Stage\domain_router.py",
    '--upload', ".tmp\8093-body-temperature-answer-integrity-20260814\delta-plan.json=$Stage\delta-plan.json",
    '--upload', "tools\remote_guarded_deploy_8093_mcp_gold.ps1=$Stage\remote_guarded_deploy_8093_mcp_gold.ps1",
    '--upload', "tools\verify_8093_mcp_gold_sse_once.py=$Stage\verify_8093_mcp_gold_sse_once.py",
    '--upload', "tools\run_8093_body_temperature_answer_integrity_deploy_20260814.ps1=$Stage\run_deploy.ps1"
)
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Upload-only staging failed.' }
