$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Base = "http://10.10.181.205:8080"
$IndexUri = "$Base/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht"
$PostUri = "$Base/demo/reportServlet?action=8"
$ReportTime = "2026-08-07 00:00:00"
$ProdCenterCode = "2D012"
$OutFile = "C:\Users\Administrator\AppData\Local\Temp\imes_report_2d012_20260807.html"

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
Invoke-WebRequest -Uri $IndexUri -UseBasicParsing -WebSession $session -TimeoutSec 20 | Out-Null

$body = @{
    time1 = $ReportTime
    prodcentercode = $ProdCenterCode
    hiddenParams = "sht=mes/jn_ts_glbb_tb.sht;"
    resultContainer = "reportContainer"
    resultPage = "queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg217"
}

$first = Invoke-WebRequest -Uri $PostUri -UseBasicParsing -WebSession $session -Method Post -Body $body -ContentType "application/x-www-form-urlencoded" -TimeoutSec 30
$firstContent = [string]$first.Content
$parts = $firstContent.Split(@("|||"), 2, [System.StringSplitOptions]::None)
if ($parts.Count -ne 2) {
    throw "报表第一跳返回格式不含 |||：$firstContent"
}
$nextUrl = $parts[0]
if ($nextUrl.StartsWith("http")) {
    $nextUri = $nextUrl
} else {
    $nextUri = "$Base/demo/reportJsp/$nextUrl"
}
$nextArgs = $parts[1]

$response = Invoke-WebRequest -Uri $nextUri -UseBasicParsing -WebSession $session -Method Post -Body $nextArgs -ContentType "application/x-www-form-urlencoded" -TimeoutSec 60
$content = [string]$response.Content
Set-Content -LiteralPath $OutFile -Value $content -Encoding UTF8

[pscustomobject]@{
    ok = $true
    status = [int]$response.StatusCode
    length = $content.Length
    first_length = $firstContent.Length
    next_uri = $nextUri
    report_time = $ReportTime
    prodcentercode = $ProdCenterCode
    title = [regex]::Match($content, "<title>(.*?)</title>", "IgnoreCase").Groups[1].Value
    has_fuel_ratio = $content.Contains("燃料比")
    has_material_speed = $content.Contains("料速")
    has_silicon = $content.Contains("硅")
    has_heat_section = $content.Contains("炉 前 出  铁 情 况")
    out_file = $OutFile
} | ConvertTo-Json -Compress
