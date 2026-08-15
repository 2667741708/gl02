[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_trace_20260814'
$Expected = [ordered]@{
    'frontend_dashboard_v3.server.html' = 'E63D80BEAB1AF72CD0650252881FEA70E9831D26CF0762BB97D03735A45B6B1A'
    'ollama_proxy_server.py' = '3F46FD86D458EA73B7060841BBCB6C017E7521E1F28A39651700965C997C59C2'
    'domain_router.py' = '92C8015FE14A26DD48B86D2CBE6C612C28F054F4EE06A284D25EC0CFE06F886D'
    'delta-plan.json' = '92703E6E6CA63B8E0AC5D1000FB8A8F6A58C14644D36FDCE3DE15346DD1AC8EB'
    'remote_guarded_deploy_8093_mcp_gold.ps1' = 'B6F094C179EF08654C8E962B3F68FDFF879D4EEFB8345C159C2C785255C0D05B'
    'verify_8093_mcp_gold_sse_once.py' = '14A75F112E1CB03260294B0B39AD4EBC802C8C578A9CDE0490CAAD03A96EAEFB'
}
$Actual = [ordered]@{}
foreach ($Name in $Expected.Keys) {
    $Path = Join-Path $Stage $Name
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing staged file: $Name" }
    $Hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($Hash -ne $Expected[$Name]) { throw "Staged hash mismatch: $Name $Hash" }
    $Actual[$Name] = $Hash
}
[ordered]@{
    ok = $true
    schema = 'bf.8093-body-temperature-trace-stage-probe.v1'
    stage = $Stage
    hashes = $Actual
    production_write_performed = $false
} | ConvertTo-Json -Depth 5
