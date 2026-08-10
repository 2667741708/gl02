$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$outDir = 'C:\Users\Administrator\AppData\Local\Temp\foreman_pspace_search_20260806'
$files = @(Get-ChildItem -LiteralPath $outDir -ErrorAction SilentlyContinue)
$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like '*run_pspace_text_search_with_site_credentials.py*'
})
foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force
}
[ordered]@{
    files = @($files | Select-Object Name, Length, LastWriteTime)
    stopped_search_pids = @($processes | ForEach-Object { $_.ProcessId })
} | ConvertTo-Json -Depth 4
