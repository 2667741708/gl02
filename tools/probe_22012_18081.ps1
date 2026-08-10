$ErrorActionPreference = 'Continue'
$rows = netstat -ano | Select-String ':18081'
foreach ($row in $rows) { Write-Output $row.Line }
$pids = @($rows | ForEach-Object {
    $parts = ($_.Line -split '\s+') | Where-Object { $_ }
    if ($parts.Count -gt 4) { $parts[4] }
}) | Select-Object -Unique
foreach ($processId in $pids) {
    Write-Output ('PID=' + $processId)
    Get-CimInstance Win32_Process -Filter ('ProcessId=' + $processId) |
        Select-Object ProcessId,Name,ExecutablePath,CommandLine |
        Format-List | Out-String | Write-Output
}
