[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
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

$Targets = @(
    '高炉前端数据\智能助手\backend\diagnosis_review.py',
    '高炉前端数据\智能助手\backend\diagnosis_model_review.py',
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\assets\bf-diagnosis-review-local.js',
    '高炉前端数据\assets\bf-diagnosis-manual-score-local.js'
)
$Hashes = [ordered]@{}
foreach ($Relative in $Targets) {
    $Path = Join-Path $Root $Relative
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing production target: $Path"
    }
    $Hashes[$Relative] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

$Ports = [ordered]@{}
foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 8892, 11434)) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $Ports[[string]$Port] = if ($Listener) { [int]$Listener.OwningProcess } else { $null }
}
$Latest = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/latest?cb=abc33-b4-source-probe' -TimeoutSec 30
$Detail = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/B4/detail?cb=abc33-b4-source-probe' -TimeoutSec 30
$Context = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/diagnosis-review-context?cb=abc33-b4-source-probe' -TimeoutSec 30
$B4 = @($Latest.rules | Where-Object { $_.rule_id -eq 'B4' }) | Select-Object -First 1

[pscustomobject]@{
    schema = 'bf.8093.abc33-b4-score-source.probe.v1'
    ok = $true
    pwsh = [ordered]@{ edition = $PSVersionTable.PSEdition; version = $PSVersionTable.PSVersion.ToString() }
    service_8093 = (Get-Service -Name 'BFV4PreviewProxy8093' -ErrorAction Stop).Status.ToString()
    listener_pids = $Ports
    hashes = $Hashes
    latest = [ordered]@{
        evaluation_id = $Latest.evaluation_id
        evaluation_ts = $Latest.evaluation_ts
        batch_state = $Latest.batch_state
        b4_score = $B4.score
        b4_status = $B4.status
    }
    detail = [ordered]@{
        evaluation_id = $Detail.evaluation_id
        evaluation_ts = $Detail.evaluation_ts
        batch_state = $Detail.batch_state
        score = $Detail.detail.score
    }
    review_context = [ordered]@{
        enabled = $Context.enabled
        snapshot_id = $Context.context.snapshot_id
        diagnosis_ts = $Context.context.diagnosis_ts
        legacy_hot = $Context.context.raw_scores.hot
        display_hot = $Context.context.display_scores.hot
        score_contract_version = $Context.context.score_contract_version
        source_rule_id = $Context.context.score_sources.hot.rule_id
    }
} | ConvertTo-Json -Depth 8
