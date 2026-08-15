[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This script requires PowerShell 7 Core.'
}

$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$BaseUri = 'http://127.0.0.1:8892'
$ObservedAt = '2026-08-09T22:00:00+08:00'
$WindowStart = '2026-08-09T20:00:00+08:00'
$WindowEnd = '2026-08-10T06:00:00+08:00'
$IdempotencyKey = 'hcz-manual:GL02:20260809T220000:up:v1'

function Encode-QueryValue {
    param([Parameter(Mandatory)][string]$Value)
    return [Uri]::EscapeDataString($Value)
}

$ContextQuery = 'observed_at={0}&start={1}&end={2}' -f `
    (Encode-QueryValue $ObservedAt), `
    (Encode-QueryValue $WindowStart), `
    (Encode-QueryValue $WindowEnd)
$Context = Invoke-RestMethod -Method Get -Uri "$BaseUri/api/hcz-label-context?$ContextQuery" -TimeoutSec 90

if (-not $Context.ok -or -not $Context.blind_to_model -or $Context.model_outputs_included) {
    throw 'HCZ label context failed the blind-evidence contract.'
}
if ($Context.source_data_hash -notmatch '^[a-f0-9]{64}$') {
    throw 'HCZ label context did not return a valid source_data_hash.'
}

$ListQuery = 'start={0}&end={1}&limit=50' -f `
    (Encode-QueryValue '2026-08-09T00:00:00+08:00'), `
    (Encode-QueryValue '2026-08-10T23:59:59+08:00')
$Before = Invoke-RestMethod -Method Get -Uri "$BaseUri/api/hcz-labels?$ListQuery" -TimeoutSec 30
$ExactBefore = @($Before.labels | Where-Object {
    $_.observed_at -eq $ObservedAt -and $_.movement_label -eq 'up'
})
if ($ExactBefore.Count -gt 0) {
    throw "An upward HCZ label already exists at $ObservedAt; refusing to append a second event."
}

$Payload = [ordered]@{
    idempotency_key = $IdempotencyKey
    observed_at = $ObservedAt
    source_window_start = $WindowStart
    source_window_end = $WindowEnd
    root_level_label = 'uncertain'
    movement_label = 'up'
    center_height_m = $null
    thickness_m = $null
    eccentric_sector = 'uncertain'
    confidence_grade = 4
    evidence_codes = @('temperature_pattern', 'top_condition', 'other')
    note = '高炉长现场确认：2026-08-09软熔带上移。pSpace四点顶温直读（PS_HIS_AVERAGE）：20时A/B/C/D=108.607/110.008/107.843/110.860℃，四点均温109.330℃；22时=126.278/122.912/125.063/124.660℃，均温124.728℃，较20时上升15.398℃；23时均温125.640℃。四点同向上升，非单点突变。pSpace审计证据SHA-256=14a3d5fc9bc90897a59ab2e8f570eec3e69cf8e1a5f7c752e37041632f8e2e85。该记录是专家弱标签，不代表直接HCZ高度实测；绝对位置仍为uncertain。'
    operator_name = '高炉长现场确认'
    source_page = '/hcz-labeling.html'
    source_data_hash = $Context.source_data_hash
}
$JsonBody = $Payload | ConvertTo-Json -Depth 8 -Compress
$Headers = @{ Origin = $BaseUri }
$Saved = Invoke-RestMethod -Method Post -Uri "$BaseUri/api/hcz-labels" -Headers $Headers -ContentType 'application/json; charset=utf-8' -Body $JsonBody -TimeoutSec 60

$After = Invoke-RestMethod -Method Get -Uri "$BaseUri/api/hcz-labels?$ListQuery" -TimeoutSec 30
$Verified = @($After.labels | Where-Object {
    $_.observed_at -eq $ObservedAt -and
    $_.movement_label -eq 'up' -and
    $_.source_data_hash -eq $Context.source_data_hash
})
if ($Verified.Count -ne 1) {
    throw "Expected exactly one verified upward label, found $($Verified.Count)."
}

[ordered]@{
    ok = $true
    context = [ordered]@{
        source_data_hash = $Context.source_data_hash
        context_mode = $Context.context_mode
        measurement_record_count = $Context.measurement_record_count
        primary_coverage = $Context.primary_coverage
        blind_to_model = $Context.blind_to_model
        model_outputs_included = $Context.model_outputs_included
    }
    before_count = $Before.count
    saved = $Saved.label
    verified_count = $Verified.Count
    verified = $Verified[0]
} | ConvertTo-Json -Depth 10
