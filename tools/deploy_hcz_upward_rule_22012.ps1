param([string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

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
$RemoteDeploy = Join-Path $Root 'tools\remote_guarded_deploy_hcz_upward_rule_8093.ps1'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\hcz_upward_rule_20260810'
$Uploads = @(
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py')=$Stage\ollama_proxy_server.py",
    "$(Join-Path $Root '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py')=$Stage\hcz_upward_rule_api.py",
    "$(Join-Path $Root '炉况规则引擎\features\hcz_upward_expert_rule.py')=$Stage\hcz_upward_expert_rule.py",
    "$(Join-Path $Root '炉况规则引擎\config\hcz_upward_expert_rule.yaml')=$Stage\hcz_upward_expert_rule.yaml",
    "$(Join-Path $Root '高炉前端数据\hcz_upward_rule.html')=$Stage\hcz_upward_rule.html",
    "$(Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.css')=$Stage\hcz-upward-rule.css",
    "$(Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.js')=$Stage\hcz-upward-rule.js"
)
foreach ($Path in @($RemoteExec, $RemoteDeploy) + ($Uploads | ForEach-Object { ($_ -split '=', 2)[0] })) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required local file missing: $Path"
    }
}
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$Arguments = @($RemoteExec, '--allow-agents-password', '--no-profile', '--timeout', '60', '--workdir', $RemoteRoot, '--upload-only')
foreach ($Upload in $Uploads) {
    $Arguments += @('--upload', $Upload)
}
& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw 'HCZ upward-rule staging failed; production was not changed.'
}
& $Python $RemoteExec --allow-agents-password --no-profile --timeout 240 --workdir $RemoteRoot --script $RemoteDeploy
if ($LASTEXITCODE -ne 0) {
    throw 'HCZ upward-rule deployment failed; inspect rollback evidence.'
}
