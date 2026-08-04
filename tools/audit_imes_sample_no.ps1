param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [string]$HeatAlignmentCsv = ''
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

function Format-RelationKey {
    param(
        [int]$Furnace,
        [int]$Year,
        [int]$Month,
        [int]$Group
    )

    return '{0}-{1:D2}-{2:D2}-{3:D3}' -f @($Furnace, $Year, $Month, $Group)
}

$rows = Import-Csv -LiteralPath $CsvPath
$parsed = [System.Collections.Generic.List[object]]::new()
$dateMismatchRows = [System.Collections.Generic.List[object]]::new()
$formatFail = 0
$dateMismatch = 0
$furnaceMismatch = 0

foreach ($row in $rows) {
    if ($row.si_sample_no -notmatch '^(?<furnace>\d)(?<yy>\d{2})(?<month>\d{2})-(?<group>\d{3})-(?<seq>\d{3})$') {
        $formatFail += 1
        continue
    }

    $sampleFurnace = [int]$Matches.furnace
    $sampleYear = [int]$Matches.yy
    $sampleMonth = [int]$Matches.month
    $sampleGroup = [int]$Matches.group
    $sampleSequence = [int]$Matches.seq
    $resultTime = [datetime]$row.si_result_ts

    if ($sampleYear -ne ($resultTime.Year % 100) -or $sampleMonth -ne $resultTime.Month) {
        $dateMismatch += 1
        $dateMismatchRows.Add([pscustomobject]@{
            sample = $row.si_sample_no
            result_ts = $row.si_result_ts
        })
    }
    if ($row.furnace_no -and $sampleFurnace -ne [int]$row.furnace_no) {
        $furnaceMismatch += 1
    }

    $parsed.Add([pscustomobject]@{
        sample = $row.si_sample_no
        furnace = $sampleFurnace
        yy = $sampleYear
        month = $sampleMonth
        group = $sampleGroup
        seq = $sampleSequence
        ts = $resultTime
        relation_key = Format-RelationKey $sampleFurnace $sampleYear $sampleMonth $sampleGroup
    })
}

$monthSummary = $parsed |
    Group-Object { '{0:D2}-{1:D2}' -f $_.yy, $_.month } |
    ForEach-Object {
        $groupRows = $_.Group
        [pscustomobject]@{
            ym = $_.Name
            rows = $groupRows.Count
            group_min = ($groupRows.group | Measure-Object -Minimum).Minimum
            group_max = ($groupRows.group | Measure-Object -Maximum).Maximum
            seq_min = ($groupRows.seq | Measure-Object -Minimum).Minimum
            seq_max = ($groupRows.seq | Measure-Object -Maximum).Maximum
            distinct_groups = ($groupRows.group | Sort-Object -Unique).Count
        }
    }

$summary = [pscustomobject]@{
    rows = $rows.Count
    valid = $parsed.Count
    format_fail = $formatFail
    date_mismatch = $dateMismatch
    furnace_mismatch = $furnaceMismatch
    duplicate_sample_nos = (
        $rows |
            Group-Object si_sample_no |
            Where-Object Count -gt 1
    ).Count
}

$heatRelation = $null
if ($HeatAlignmentCsv) {
    $heatRows = Import-Csv -LiteralPath $HeatAlignmentCsv
    $heatByKey = @{}
    foreach ($heat in $heatRows) {
        if ($heat.meltno -notmatch '^(?<furnace>\d+)#(?<year>\d{4})(?<month>\d{2})(?<day>\d{2})-(?<group>\d{3})$') {
            continue
        }
        $key = Format-RelationKey `
            ([int]$Matches.furnace) `
            ([int]$Matches.year % 100) `
            ([int]$Matches.month) `
            ([int]$Matches.group)
        $heatByKey[$key] = $heat
    }

    $windowStart = if ($heatRows.Count) {
        ($heatRows | ForEach-Object { [datetime]$_.open_ts } | Measure-Object -Minimum).Minimum
    } else {
        $null
    }
    $windowEnd = if ($heatRows.Count) {
        ($heatRows | ForEach-Object {
            if ($_.close_ts) { [datetime]$_.close_ts } else { [datetime]$_.open_ts }
        } | Measure-Object -Maximum).Maximum
    } else {
        $null
    }
    $windowSamples = @(
        $parsed | Where-Object {
            $null -ne $windowStart -and
            $_.ts -ge ($windowStart - [timespan]::FromHours(6)) -and
            $_.ts -le ($windowEnd + [timespan]::FromHours(12))
        }
    )
    $matchedSamples = @($windowSamples | Where-Object { $heatByKey.ContainsKey($_.relation_key) })
    $matchedGroups = @($matchedSamples.relation_key | Sort-Object -Unique)
    $samplesPerHeat = @(
        $matchedSamples |
            Group-Object relation_key |
            Group-Object Count |
            Sort-Object { [int]$_.Name } |
            ForEach-Object {
                [pscustomobject]@{
                    samples_per_heat = [int]$_.Name
                    heat_count = $_.Count
                }
            }
    )
    $heatRelation = [pscustomobject]@{
        official_heat_rows = $heatByKey.Count
        sample_rows_in_time_window = $windowSamples.Count
        matched_sample_rows = $matchedSamples.Count
        unmatched_sample_rows = $windowSamples.Count - $matchedSamples.Count
        matched_distinct_heat_suffixes = $matchedGroups.Count
        official_heats_with_sample = @(
            $heatByKey.Keys | Where-Object { $_ -in $matchedGroups }
        ).Count
        samples_per_heat_distribution = $samplesPerHeat
    }
}

[pscustomobject]@{
    summary = $summary
    by_month = @($monthSummary | Sort-Object ym)
    recent_examples = @($parsed | Sort-Object ts -Descending | Select-Object -First 8)
    date_mismatch_examples = @($dateMismatchRows | Select-Object -First 20)
    heat_relation = $heatRelation
} | ConvertTo-Json -Depth 5
