$ErrorActionPreference = 'Stop'
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$uri = 'http://10.10.181.205:8080/demo/reportServlet?action=8'
$body = @{
    time1 = '2026-08-07'
    prodcentercode = '2D012'
    hiddenParams = 'sht=mes/jn_ts_glbb_tb.sht;'
    resultContainer = 'reportContainer'
    resultPage = 'queryInput.jsp?sht=mes%2Fjn_ts_glbb_tb.sht&adp=&dataFile=&fileType=json&sgid=sg213'
}
$response = Invoke-WebRequest -UseBasicParsing -Method Post -WebSession $session -Uri $uri -Body $body -TimeoutSec 60
Write-Output ('STATUS=' + $response.StatusCode)
Write-Output ('CONTENT_TYPE=' + $response.Headers['Content-Type'])
Write-Output ('CONTENT_LENGTH=' + $response.Content.Length)
Write-Output ('RESPONSE_URI=' + $response.BaseResponse.ResponseUri.AbsoluteUri)
$limit = [Math]::Min(1000, $response.Content.Length)
Write-Output $response.Content.Substring(0, $limit)
$parts = $response.Content -split '\|\|\|', 2
$queryPath = $parts[0]
$queryBody = $parts[1]
$queryUri = 'http://10.10.181.205:8080/demo/reportJsp/' + $queryPath
$queryResponse = Invoke-WebRequest -UseBasicParsing -Method Post -WebSession $session -Uri $queryUri -Body $queryBody -TimeoutSec 60
Write-Output ('QUERY_STATUS=' + $queryResponse.StatusCode)
Write-Output ('QUERY_CONTENT_TYPE=' + $queryResponse.Headers['Content-Type'])
Write-Output ('QUERY_CONTENT_LENGTH=' + $queryResponse.Content.Length)
$queryLimit = [Math]::Min(1200, $queryResponse.Content.Length)
Write-Output $queryResponse.Content.Substring(0, $queryLimit)
