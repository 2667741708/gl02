$ports = 8093,8094,8768,8770,11434
$rows = foreach ($p in $ports) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    [pscustomobject]@{ port = $p; pid = if ($c) { $c.OwningProcess } else { $null } }
}
$svc = Get-Service -Name 'BFV4PreviewWs8768','V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue | Select-Object Name,Status
$rows | ConvertTo-Json -Compress
$svc | ConvertTo-Json -Compress
$r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/' -TimeoutSec 10
Write-Output ('http8094=' + $r.StatusCode)
