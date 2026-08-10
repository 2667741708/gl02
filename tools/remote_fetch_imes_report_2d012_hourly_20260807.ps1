$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$base = 'http://10.10.181.205:8080'
$indexUri = "$base/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht"
$postUri = "$base/demo/reportServlet?action=8"
$outDir = Join-Path $env:TEMP 'imes_report_2d012_hourly_20260807'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Invoke-ReportFetch {
    param(
        [string]$ReportTime,
        [string]$OutputPath,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session
    )

    $body = @{
        time1 = $ReportTime
        prodcentercode = '2D012'
        hiddenParams = 'sht=mes/jn_ts_glbb_tb.sht;'
        resultContainer = 'reportContainer'
        resultPage = 'queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg217'
    }

    $first = Invoke-WebRequest -Uri $postUri -Method Post -Body $body -UseBasicParsing -WebSession $Session -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 60
    $text = $first.Content
    $parts = $text -split '\|\|\|', 2
    if ($parts.Count -ne 2) {
        throw "Unexpected first response for $ReportTime"
    }

    $nextUrl = $parts[0]
    if ($nextUrl -notmatch '^https?://') {
        $nextUrl = "$base/demo/reportJsp/$nextUrl"
    }

    $second = Invoke-WebRequest -Uri $nextUrl -Method Post -Body $parts[1] -ContentType 'application/x-www-form-urlencoded' -UseBasicParsing -WebSession $Session -TimeoutSec 60
    Set-Content -LiteralPath $OutputPath -Value $second.Content -Encoding UTF8

    [pscustomobject]@{
        report_time = $ReportTime
        bytes = $second.Content.Length
        output = $OutputPath
    }
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri $indexUri -UseBasicParsing -WebSession $session -TimeoutSec 20 | Out-Null

$results = @()
$date = '2026-08-07'
foreach ($hour in 0..23) {
    $reportTime = '{0} {1:D2}:30:00' -f $date, $hour
    $safeHour = '{0:D2}30' -f $hour
    $fileName = 'imes_report_2d012_20260807_{0}.html' -f $safeHour
    $path = Join-Path $outDir $fileName
    try {
        $results += Invoke-ReportFetch -ReportTime $reportTime -OutputPath $path -Session $session
    } catch {
        $results += [pscustomobject]@{
            report_time = $reportTime
            error = $_.Exception.Message
            output = $path
        }
    }
}

$results | ConvertTo-Json -Depth 3
