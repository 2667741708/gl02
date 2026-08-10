$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$stage='C:\Users\Administrator\AppData\Local\Temp\abc33_common_factors'
$script=Join-Path $stage 'deploy_8768.ps1'
$stdout=Join-Path $stage 'deploy_8768.stdout.log'
$stderr=Join-Path $stage 'deploy_8768.stderr.log'
if(-not(Test-Path -LiteralPath $script)){throw 'deployment script is unavailable'}
foreach($path in $stdout,$stderr){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}}
$arguments="-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$process=Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr -ArgumentList $arguments
Write-Output ('pid='+$process.Id)
Write-Output ('stdout='+$stdout)
Write-Output ('stderr='+$stderr)
