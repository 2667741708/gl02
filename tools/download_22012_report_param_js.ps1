$ErrorActionPreference = 'Stop'
$uri = 'http://10.10.181.205:8080/demo/reportServlet?action=10&file=%2Fcom%2Fraqsoft%2Freport%2Fview%2Fhtml%2FparamForm.js'
$outPath = 'C:\Users\Administrator\AppData\Local\Temp\paramForm.js'
$response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 30
[IO.File]::WriteAllText($outPath, $response.Content, [Text.UTF8Encoding]::new($false))
Write-Output ('STATUS=' + $response.StatusCode)
Write-Output ('BYTES=' + ([Text.Encoding]::UTF8.GetByteCount($response.Content)))
