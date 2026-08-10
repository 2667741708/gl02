$ErrorActionPreference = "Stop"
$matches = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*sync_from_243_pg.py*" -and
    $_.CommandLine -like "*Q_soft_water*"
}
if (@($matches).Count -ne 1) { throw ("expected one exact cooling sync process, found " + @($matches).Count) }
$target = $matches | Select-Object -First 1
Write-Output ("stopping_pid=" + $target.ProcessId)
Stop-Process -Id $target.ProcessId -Force
