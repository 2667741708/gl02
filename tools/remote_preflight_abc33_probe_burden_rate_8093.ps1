$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$RelativeTargets = @(
    '自动诊断服务\abc_burden_rate.py',
    '自动诊断服务\abc_public_review.py',
    '自动诊断服务\abc_feature_builder.py',
    '自动诊断服务\abc_factor_audit.py',
    '自动诊断服务\config\abc_furnace_rules.v1.json'
)
$Hashes = [ordered]@{}
foreach ($Relative in $RelativeTargets) {
    $Target = Join-Path $Root $Relative
    $Hashes[$Target] = if (Test-Path -LiteralPath $Target -PathType Leaf) { (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash } else { $null }
}
$Listeners = [ordered]@{}
foreach ($Port in @(8093,8094,8768,8770,5432,11434)) {
    $Row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    $Listeners[[string]$Port] = if ($Row) { [int]$Row.OwningProcess } else { $null }
}
$Service = Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop
$Http = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?cb=probe-burden-preflight' -TimeoutSec 20
[ordered]@{
    schema='bf.deploy.remote-state.v1'; requirement_id='REQ-ABC33-PSPACE-PROBE-BURDEN-RATE-20260811';
    ok=($Service.Status -eq 'Running' -and $Http.StatusCode -eq 200 -and -not ($Listeners.Values -contains $null));
    powershell=$PSVersionTable.PSVersion.ToString(); edition=$PSVersionTable.PSEdition;
    service=$Service.Status.ToString(); http_8093=[int]$Http.StatusCode; listeners=$Listeners; targets=$Hashes
} | ConvertTo-Json -Depth 6
