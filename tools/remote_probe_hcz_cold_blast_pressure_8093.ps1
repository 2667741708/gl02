[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'REQ-HCZ-COLD-BLAST-PRESSURE-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '炉况规则引擎\config\hcz_upward_expert_rule.yaml'
$Ports = @(8093, 8094, 8768, 8770, 5432, 8892, 11434)
$Listeners = [ordered]@{}
foreach ($Port in $Ports) {
    $Connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $Listeners[[string]$Port] = if ($Connection) { [int]$Connection.OwningProcess } else { $null }
}
$Exists = Test-Path -LiteralPath $Target -PathType Leaf
$Text = if ($Exists) { Get-Content -LiteralPath $Target -Raw -Encoding UTF8 } else { '' }
$Api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/hcz-upward-rule?probe=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())" -TimeoutSec 120

[pscustomobject]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = $RequirementId
    targets = [ordered]@{
        $Target = [ordered]@{
            exists = $Exists
            sha256 = if ($Exists) { (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash } else { $null }
        }
    }
    runtime = [ordered]@{
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        service_8093 = (Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop).Status.ToString()
        listeners = $Listeners
        api_ok = [bool]$Api.ok
        api_pressure_label = [string]$Api.metrics.blast_pressure.label
        config_uses_hot_blast = $Text.Contains('variables: [P_blast]')
        config_uses_cold_blast = $Text.Contains('variables: [P_blast_cold]')
    }
} | ConvertTo-Json -Depth 8
