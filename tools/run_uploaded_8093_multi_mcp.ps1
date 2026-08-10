$ErrorActionPreference = 'Stop'
$remoteScript = 'C:\Users\Administrator\AppData\Local\Temp\remote_guarded_deploy_8093_multi_mcp.ps1'
if (-not (Test-Path -LiteralPath $remoteScript -PathType Leaf)) {
    throw "uploaded deployment script is missing: $remoteScript"
}
$body = Get-Content -LiteralPath $remoteScript -Raw -Encoding UTF8
Invoke-Expression $body
exit $LASTEXITCODE
