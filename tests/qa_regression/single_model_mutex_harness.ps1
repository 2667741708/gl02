[CmdletBinding()]
param([Parameter(Mandatory)][string]$Candidate,[Parameter(Mandatory)][string]$Workdir,[switch]$Busy)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8=[Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=$Utf8
[Console]::OutputEncoding=$Utf8
$OutputEncoding=$Utf8
$PSDefaultParameterValues['*:Encoding']='utf8'
$Text=[IO.File]::ReadAllText($Candidate,$Utf8)
$Marker='$mutex = [Threading.Mutex]::new($false, "Global\BFOllamaModelSwitch")'
$Offset=$Text.IndexOf($Marker,[StringComparison]::Ordinal)
if ($Offset -lt 0 -or $Text.LastIndexOf($Marker,[StringComparison]::Ordinal) -ne $Offset) { throw 'Actual mutex dispatch block missing' }
$Name='Global\QASyntheticModelGuard-'+[guid]::NewGuid().ToString('N')
$Tail=$Text.Substring($Offset).Replace('Global\BFOllamaModelSwitch',$Name)
$Header='$Action="Repair"; function Invoke-Repair { return @{synthetic_repair_called=$true} }; function ConvertTo-PublicSafeText {param($Value) return "synthetic_dispatch_failed"}'
$Script=Join-Path $Workdir 'synthetic-mutex-dispatch.ps1'
[IO.File]::WriteAllText($Script,$Header+"`n"+$Tail,$Utf8)
$Mutex=[Threading.Mutex]::new($false,$Name)
$Taken=$false
try {
    if ($Busy) { $Taken=$Mutex.WaitOne(0);if (-not $Taken) { throw 'Synthetic mutex ownership failed' } }
    $Info=[Diagnostics.ProcessStartInfo]::new()
    $Info.FileName=(Join-Path $PSHOME 'pwsh.exe')
    foreach ($Argument in @('-NoLogo','-NoProfile','-File',$Script)) { $Info.ArgumentList.Add($Argument) }
    $Info.UseShellExecute=$false
    $Info.CreateNoWindow=$true
    $Info.RedirectStandardOutput=$true
    $Info.RedirectStandardError=$true
    $Process=[Diagnostics.Process]::Start($Info)
    if (-not $Process.WaitForExit(10000)) { $Process.Kill();throw 'Synthetic child dispatch timeout' }
    $Result=$Process.StandardOutput.ReadToEnd() | ConvertFrom-Json
    if ($Process.ExitCode -ne 0) { throw 'Synthetic child dispatch failed' }
    $Result | ConvertTo-Json -Depth 8
} finally {
    if ($Taken) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
