$ErrorActionPreference = 'Stop'
$python = 'C:\Program Files\Python311\python.exe'
$script = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.py'
$output = 'C:\Users\Administrator\AppData\Local\Temp\audit_22012_pspace_cooling_daily.full.txt'
& $python $script | Out-File -LiteralPath $output -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw ('audit failed with exit code ' + $LASTEXITCODE) }
Write-Output ('OUTPUT_BYTES=' + (Get-Item -LiteralPath $output).Length)
