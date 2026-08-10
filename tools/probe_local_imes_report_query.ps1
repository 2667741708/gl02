$ErrorActionPreference = 'Stop'
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base = 'http://10.30.220.12:18084'
$body = @{
    time1 = '2026-08-07'
    prodcentercode = '2D012'
    hiddenParams = 'sht=mes/jn_ts_glbb_tb.sht;'
    resultContainer = 'reportContainer'
    resultPage = 'queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg213'
}
$first = Invoke-WebRequest -UseBasicParsing -Method Post -WebSession $session -Uri ($base + '/demo/reportServlet?action=8') -Body $body -TimeoutSec 60
$parts = $first.Content -split '\|\|\|', 2
if ($parts.Count -ne 2) { throw 'reportServlet response did not contain query path and args' }
$queryUri = $base + '/demo/reportJsp/' + $parts[0]
$query = Invoke-WebRequest -UseBasicParsing -Method Post -WebSession $session -Uri $queryUri -Body $parts[1] -TimeoutSec 60
$outPath = 'logs\jn_ts_glbb_tb_query_20260807.html'
[IO.File]::WriteAllText($outPath, $query.Content, [Text.UTF8Encoding]::new($false))
[pscustomobject]@{
    FirstStatus = $first.StatusCode
    QueryStatus = $query.StatusCode
    QueryLength = $query.Content.Length
    HasFuelRatio = ($query.Content -match ([char]0x71C3 + [char]0x6599 + [char]0x6BD4))
    HasMaterialRate = ($query.Content -match ([char]0x6599 + [char]0x901F))
    HasSecondFurnace = ($query.Content -match '2#|2D012')
    QueryFile = (Resolve-Path -LiteralPath $outPath).Path
} | Format-List
