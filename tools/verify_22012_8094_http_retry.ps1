$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$status = 0
for ($attempt=1; $attempt -le 3; $attempt++) {
    try {
        $status = [int](Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 30).StatusCode
        if ($status -eq 200) { break }
    } catch { Start-Sleep -Seconds 5 }
}
Write-Output ("http8094=" + $status)
if ($status -ne 200) { exit 2 }
