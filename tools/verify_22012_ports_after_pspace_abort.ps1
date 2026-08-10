$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ports = 8093,8094,8768,8770,11434
$result = [ordered]@{}
foreach ($port in $ports) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $result["p$port"] = if ($listener) { [int]$listener.OwningProcess } else { $null }
}
$result["service8768"] = (Get-Service BFV4PreviewWs8768).Status.ToString()
try { $result["http8094"] = [int](Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 20).StatusCode } catch { $result["http8094"] = 0 }
$result | ConvertTo-Json
