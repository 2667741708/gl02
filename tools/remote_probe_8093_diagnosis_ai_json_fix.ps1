[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '高炉前端数据\智能助手\backend\diagnosis_review.py'
$Ports = @(8093, 8094, 8768, 8770, 5432, 11434)

function Get-ListenerPidMap {
    param([int[]]$RequestedPorts)
    $Found = @{}
    Get-NetTCPConnection -State Listen -ErrorAction Stop | ForEach-Object {
        $Port = [int]$_.LocalPort
        if ($RequestedPorts -contains $Port -and -not $Found.ContainsKey($Port)) {
            $Found[$Port] = [int]$_.OwningProcess
        }
    }
    $Result = [ordered]@{}
    foreach ($Port in $RequestedPorts) {
        $Result[[string]$Port] = $Found[$Port]
    }
    return $Result
}

if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {
    throw "Production target missing: $Target"
}
$Listeners = Get-ListenerPidMap -RequestedPorts $Ports
$MissingPorts = @($Ports | Where-Object { -not $Listeners[[string]$_] })
$Service = Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop
$Page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?cb=diag-json-preflight' -TimeoutSec 30
$KnowledgeQuery = [uri]::EscapeDataString('高炉透气性变差时的处置原则')
$Knowledge = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/qa/knowledge/search?q=$KnowledgeQuery&top_k=2" -TimeoutSec 30

[ordered]@{
    schema = 'ops.8093.diagnosis-ai-json-fix.preflight.v1'
    ok = $Service.Status.ToString() -eq 'Running' -and $Page.StatusCode -eq 200 -and $MissingPorts.Count -eq 0
    service = [ordered]@{ name = $Service.Name; status = $Service.Status.ToString() }
    listeners = $Listeners
    missing_ports = $MissingPorts
    http_8093 = [int]$Page.StatusCode
    target = [ordered]@{
        path = $Target
        exists = $true
        sha256 = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    }
    knowledge = [ordered]@{
        ok = [bool]$Knowledge.ok
        enabled = [bool]$Knowledge.enabled
        retrieval_mode = [string]$Knowledge.retrieval_mode
        evidence_count = @($Knowledge.evidence).Count
    }
} | ConvertTo-Json -Depth 7
