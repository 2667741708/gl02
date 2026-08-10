$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$base = 'http://10.10.181.205:8080'
$indexUri = "$base/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht"
$postUri = "$base/demo/reportServlet?action=8"
$prodCenterCode = '2D012'
$outDir = Join-Path $env:TEMP 'imes_report_2d012_recent_days'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Invoke-DailyReportFetch {
    param(
        [string]$ReportTime,
        [string]$OutputPath
    )

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-WebRequest -Uri $indexUri -UseBasicParsing -WebSession $session -TimeoutSec 20 | Out-Null

    $body = @{
        time1 = $ReportTime
        prodcentercode = $prodCenterCode
        hiddenParams = 'sht=mes/jn_ts_glbb_tb.sht;'
        resultContainer = 'reportContainer'
        resultPage = 'queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg217'
    }

    $first = Invoke-WebRequest -Uri $postUri -UseBasicParsing -WebSession $session -Method Post -Body $body -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 30
    $firstContent = [string]$first.Content
    $parts = $firstContent.Split(@('|||'), 2, [System.StringSplitOptions]::None)
    if ($parts.Count -ne 2) {
        throw "报表第一跳返回格式不含 |||：$firstContent"
    }

    $nextUrl = $parts[0]
    if ($nextUrl.StartsWith('http')) {
        $nextUri = $nextUrl
    } else {
        $nextUri = "$base/demo/reportJsp/$nextUrl"
    }

    $response = Invoke-WebRequest -Uri $nextUri -UseBasicParsing -WebSession $session -Method Post -Body $parts[1] -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 60
    $content = [string]$response.Content
    Set-Content -LiteralPath $OutputPath -Value $content -Encoding UTF8

    [pscustomobject]@{
        ok = $true
        report_time = $ReportTime
        length = $content.Length
        output = $OutputPath
        has_fuel_ratio = $content.Contains('燃料比')
        has_silicon = $content.Contains('硅')
    }
}

$startDate = [datetime]'2026-07-22'
$endDate = [datetime]'2026-08-08'
$results = @()
$date = $startDate
while ($date -le $endDate) {
    $reportTime = $date.ToString('yyyy-MM-dd 00:00:00')
    $dateToken = $date.ToString('yyyyMMdd')
    $outFile = Join-Path $outDir "imes_report_2d012_$dateToken.html"
    try {
        $results += Invoke-DailyReportFetch -ReportTime $reportTime -OutputPath $outFile
    } catch {
        $results += [pscustomobject]@{
            ok = $false
            report_time = $reportTime
            error = $_.Exception.Message
            output = $outFile
        }
    }
    $date = $date.AddDays(1)
}

[pscustomobject]@{
    ok = $true
    prodcentercode = $prodCenterCode
    out_dir = $outDir
    results = $results
} | ConvertTo-Json -Depth 4
