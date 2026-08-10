$ErrorActionPreference = 'Stop'
$python = (Get-Command python).Source
$args = @(
  '.\tools\remote_22012_exec.py',
  '--allow-agents-password',
  '--no-profile',
  '--timeout', '30',
  '--script', '.\tools\remote_poll_pspace_cooling_audit.ps1'
)
$stdout = '.\logs\pspace_cooling_poll.out.log'
$stderr = '.\logs\pspace_cooling_poll.err.log'
$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Write-Output $process.Id
