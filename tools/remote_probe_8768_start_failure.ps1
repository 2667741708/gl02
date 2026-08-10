$ErrorActionPreference = 'Stop'
$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$svc = Get-Service -Name 'BFV4PreviewWs8768'
Write-Output ('SERVICE=' + $svc.Status)
$outLog = Join-Path $root 'logs\ws_8768.service.out.log'
$errLog = Join-Path $root 'logs\ws_8768.service.err.log'
Write-Output 'STDOUT_TAIL_BEGIN'
if (Test-Path -LiteralPath $outLog) { Get-Content -LiteralPath $outLog -Encoding UTF8 -Tail 120 }
Write-Output 'STDOUT_TAIL_END'
Write-Output 'STDERR_TAIL_BEGIN'
if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Encoding UTF8 -Tail 120 }
Write-Output 'STDERR_TAIL_END'
Write-Output 'SYSTEM_EVENTS_BEGIN'
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddHours(-2)} -ErrorAction SilentlyContinue |
  Where-Object { $_.Message -match 'BFV4PreviewWs8768|8768|NSSM' } |
  Select-Object -First 20 TimeCreated,Id,LevelDisplayName,Message
Write-Output 'SYSTEM_EVENTS_END'
