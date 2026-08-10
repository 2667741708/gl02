$mcp = Get-ChildItem -LiteralPath (Join-Path (Get-Location) '高炉前端数据\智能助手\mcp\bf_data_mcp_server.py')
Write-Output ("mcp_last_write=" + $mcp.LastWriteTime.ToString('s'))
$processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*ollama_proxy_server.py*' -and $_.CommandLine -like '*V4_8093_PREVIEW*' }
foreach ($process in $processes) {
  Write-Output ("proxy_pid=" + $process.ProcessId)
  Write-Output ("proxy_created=" + $process.CreationDate)
  Write-Output ("proxy_command=" + $process.CommandLine)
}
netstat -ano | Select-String ':8093'
