$uri = '/demo/reportJsp/showInput.jsp?sht=mes/jn_ts_glbb_tb.sht'
foreach ($port in @(18081, 18084)) {
  Write-Output ("port=" + $port)
  $listeners = netstat -ano | Select-String (":" + $port + ' ')
  foreach ($listener in $listeners) { Write-Output $listener.Line }
  try {
    $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 ("http://127.0.0.1:" + $port + $uri)
    Write-Output ("status=" + $response.StatusCode)
    Write-Output ("length=" + $response.RawContentLength)
    Write-Output ("title=" + ([regex]::Match($response.Content, '<title>(.*?)</title>', 'IgnoreCase').Groups[1].Value))
  } catch {
    Write-Output ("error=" + $_.Exception.Message)
  }
}
