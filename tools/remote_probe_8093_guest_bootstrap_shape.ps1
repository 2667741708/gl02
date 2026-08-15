[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$BootstrapStatus = 0
$Bootstrap = $null
try {
    $Bootstrap = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/qa/bootstrap' -TimeoutSec 20
    $BootstrapStatus = 200
}
catch {
    if ($_.Exception.Response) { $BootstrapStatus = [int]$_.Exception.Response.StatusCode }
    else { throw }
}
$Backend = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$Config = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$ConfigJson = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$EnvNames = @($ConfigJson.env.PSObject.Properties.Name)
[ordered]@{
    ok = $true
    bootstrap_http = $BootstrapStatus
    bootstrap_keys = if ($Bootstrap) { @($Bootstrap.PSObject.Properties.Name) } else { @() }
    access_mode = [string]($Bootstrap.access_mode ?? '')
    current_conversation_id = [string]($Bootstrap.current_conversation_id ?? '')
    conversation_id = [string]($Bootstrap.conversation.id ?? '')
    qa_guest_env_present = $EnvNames -contains 'BF_QA_GUEST_ENABLED'
    qa_guest_env_value = if ($EnvNames -contains 'BF_QA_GUEST_ENABLED') { [string]$ConfigJson.env.BF_QA_GUEST_ENABLED } else { '<default>' }
    backend_hash = (Get-FileHash -LiteralPath $Backend -Algorithm SHA256).Hash
    service = (Get-Service 'BFV4PreviewProxy8093').Status.ToString()
    listener_8093 = [int](Get-NetTCPConnection -LocalPort 8093 -State Listen | Select-Object -First 1).OwningProcess
} | ConvertTo-Json -Depth 6
