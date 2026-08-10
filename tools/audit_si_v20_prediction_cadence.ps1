param(
    [string]$BaseUrl = 'http://10.30.220.12:8093',
    [string]$DateFrom = '2026-08-01',
    [string]$DateTo = (Get-Date).ToString('yyyy-MM-dd')
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Convert-ToLocalDateTime([object]$Value) {
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
        return $null
    }
    return [datetime]::Parse(([string]$Value).Substring(0, 19))
}

function Get-PredictionMetrics([object[]]$Rows) {
    $evaluated = @($Rows | Where-Object { $null -ne $_.absolute_error })
    $count = $evaluated.Count
    if ($count -eq 0) {
        return [ordered]@{ evaluated = 0; mae = $null; hit_rate_abs_le_002 = $null; hit_rate_abs_le_005 = $null }
    }
    $mae = ($evaluated | Measure-Object -Property absolute_error -Average).Average
    $hit002 = @($evaluated | Where-Object { [double]$_.absolute_error -le 0.02 }).Count / $count
    $hit005 = @($evaluated | Where-Object { [double]$_.absolute_error -le 0.05 }).Count / $count
    return [ordered]@{
        evaluated = $count
        mae = [math]::Round([double]$mae, 6)
        hit_rate_abs_le_002 = [math]::Round([double]$hit002, 6)
        hit_rate_abs_le_005 = [math]::Round([double]$hit005, 6)
    }
}

$historyUri = "$BaseUrl/api/si-v20/history?date_from=$DateFrom&date_to=$DateTo&limit=1200&latest_per_heat=0"
$statusUri = "$BaseUrl/api/si-v20/status?limit=300"
$history = Invoke-RestMethod -Uri $historyUri -TimeoutSec 10
$status = Invoke-RestMethod -Uri $statusUri -TimeoutSec 10

$items = @($history.items)
$modeCounts = [ordered]@{}
foreach ($group in $items | Group-Object request_mode) {
    $modeCounts[$group.Name] = $group.Count
}

$actualByMelt = @{}
foreach ($target in @($status.targets)) {
    $actualByMelt[[string]$target.meltno] = $target
}

$hourlyDetails = foreach ($row in $items | Where-Object { $_.request_mode -eq 'hourly_schedule' }) {
    $actual = $actualByMelt[[string]$row.target_meltno]
    $requested = Convert-ToLocalDateTime $row.requested_at
    $cutoff = Convert-ToLocalDateTime $row.prediction_cutoff_ts
    $predictedOpen = Convert-ToLocalDateTime $row.target_open_ts
    $actualOpen = Convert-ToLocalDateTime $actual.open_ts
    [ordered]@{
        prediction_id = $row.prediction_id
        meltno = $row.target_meltno
        requested_at = $row.requested_at
        cutoff_ts = $row.prediction_cutoff_ts
        predicted_open_ts = $row.target_open_ts
        actual_open_ts = $actual.open_ts
        requested_before_actual_open = if ($requested -and $actualOpen) { $requested -le $actualOpen } else { $null }
        cutoff_to_actual_open_minutes = if ($cutoff -and $actualOpen) { [math]::Round(($actualOpen - $cutoff).TotalMinutes, 3) } else { $null }
        request_to_actual_open_minutes = if ($requested -and $actualOpen) { [math]::Round(($actualOpen - $requested).TotalMinutes, 3) } else { $null }
        predicted_open_minus_actual_minutes = if ($predictedOpen -and $actualOpen) { [math]::Round(($predictedOpen - $actualOpen).TotalMinutes, 3) } else { $null }
        prediction_si = $row.prediction_si_mean
        actual_si = $row.actual_si_mean
        absolute_error = $row.absolute_error
        hit_abs_le_002 = if ($null -ne $row.absolute_error) { [double]$row.absolute_error -le 0.02 } else { $null }
        hit_abs_le_005 = $row.hit_abs_le_005
    }
}

$replayLatest = @($items | Where-Object { $_.request_mode -eq 'historical_range_replay' } |
    Sort-Object requested_at -Descending |
    Group-Object target_meltno |
    ForEach-Object { $_.Group[0] })

[ordered]@{
    schema = 'ops.si-v20.prediction-cadence-audit.v1'
    audited_at = (Get-Date).ToString('o')
    date_from = $DateFrom
    date_to = $DateTo
    total_audit_rows = $items.Count
    mode_counts = $modeCounts
    hourly = [ordered]@{
        count = @($hourlyDetails).Count
        strict_preopen_count = @($hourlyDetails | Where-Object { $_.requested_before_actual_open -eq $true }).Count
        metrics = Get-PredictionMetrics @($items | Where-Object { $_.request_mode -eq 'hourly_schedule' })
        details = @($hourlyDetails)
    }
    open_minus_60_replay_unique_heat = [ordered]@{
        count = $replayLatest.Count
        metrics = Get-PredictionMetrics $replayLatest
    }
} | ConvertTo-Json -Depth 8
