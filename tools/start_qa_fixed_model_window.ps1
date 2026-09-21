[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Stage,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$WindowHash,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$PlanHash,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$BatchHash,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$CollectorHash,
    [ValidateRange(15,120)][int]$WindowMinutes = 120
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ExactStage = 'C:/Users/Administrator/AppData/Local/Temp/qa-model-window-v26-20260917-r2'
if ([IO.Path]::GetFullPath($Stage) -ne [IO.Path]::GetFullPath($ExactStage)) { throw 'Unexpected fixed-window stage' }
$Window = Join-Path $ExactStage 'window.ps1'
if ((Get-FileHash -LiteralPath $Window -Algorithm SHA256).Hash -ne $WindowHash) { throw 'Window owner hash changed' }
$Root = 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Output = Join-Path $Root 'logs/qa_model_window_v26_20260917_r2'
if (Test-Path -LiteralPath $Output) { throw 'Existing evidence; read-only recovery required, no replay' }
# A durable one-time launch claim also covers an uncertain WMI response.
$Claim = Join-Path $ExactStage 'launch.claim'
$Stream = [IO.File]::Open($Claim, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
$Stream.Dispose()
$Command = '"C:/Program Files/PowerShell/7/pwsh.exe" -NoLogo -NoProfile -WindowStyle Hidden -File "' + $Window + '" -Stage "' + $ExactStage + '" -PlanHash ' + $PlanHash + ' -BatchHash ' + $BatchHash + ' -CollectorHash ' + $CollectorHash + ' -WindowMinutes ' + $WindowMinutes
$Created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$Command}
if ($Created.ReturnValue -ne 0 -or -not $Created.ProcessId) { throw 'Launch uncertain; inspect claim and process, never replay' }
@{started=$true; pid=$Created.ProcessId; automatic_replay=$false; window_minutes=$WindowMinutes} | ConvertTo-Json -Compress
