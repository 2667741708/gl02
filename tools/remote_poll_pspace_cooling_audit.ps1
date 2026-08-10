$pidFile = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.pid'
$stdout = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.json'
$stderr = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.err.log'
$auditPid = [int](Get-Content -LiteralPath $pidFile -Encoding ASCII)
$running = $null -ne (Get-Process -Id $auditPid -ErrorAction SilentlyContinue)
$size = if (Test-Path -LiteralPath $stdout) { (Get-Item -LiteralPath $stdout).Length } else { 0 }
$errorTail = if (Test-Path -LiteralPath $stderr) { @(Get-Content -LiteralPath $stderr -Encoding UTF8 -Tail 10) } else { @() }
[pscustomobject]@{pid=$auditPid;running=$running;output_bytes=$size;error_tail=$errorTail} | ConvertTo-Json -Depth 3
