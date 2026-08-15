[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = 'D:\ProgramData\anaconda3\python.exe'
$Session = Join-Path $Root 'tools\remote_22012_session.py'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_body_temperature_statistics_git_20260814'
$Arguments = @(
    $Session, 'run', '--', '--upload-only',
    '--upload', "tools\remote_record_8093_mcp_gold_git_version.ps1=$Stage\remote_record_8093_mcp_gold_git_version.ps1",
    '--upload', "tools\run_8093_body_temperature_statistics_git_save_20260814.ps1=$Stage\run_git_save.ps1"
)
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Git-save staging failed.' }
