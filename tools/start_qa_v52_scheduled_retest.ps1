[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Root,
    [Parameter(Mandatory)][string]$Stage,
    [Parameter(Mandatory)][string]$Output,
    [Parameter(Mandatory)][ValidatePattern('^[A-Fa-f0-9]{64}$')][string]$ManifestHash
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$Python = 'C:/Program Files/Python311/pythonw.exe'
$ManifestPath = Join-Path $Stage 'manifest.private.json'
foreach ($Path in @($Root, $Stage, $Output, $Python)) {
    if ($Path.Contains('"')) { throw 'Invalid quote in launch path' }
}
$ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
$ResolvedOutput = [IO.Path]::GetFullPath($Output)
$AllowedPrefix = (Join-Path $ResolvedRoot 'logs') + [IO.Path]::DirectorySeparatorChar
if (-not $ResolvedOutput.StartsWith($AllowedPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be below runtime logs' }
if ((Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash -cne $ManifestHash.ToUpperInvariant()) { throw 'Manifest hash changed' }
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding utf8 | ConvertFrom-Json
$Required = @('worker.py', 'batch.py', 'collector.py', 'plan.private.json', 'summary.py', 'start.ps1')
if (@($Manifest.files.PSObject.Properties).Count -ne $Required.Count) { throw 'Launch file set invalid' }
foreach ($Name in $Required) {
    $Expected = $Manifest.files.PSObject.Properties[$Name].Value
    if ((Get-FileHash -LiteralPath (Join-Path $Stage $Name) -Algorithm SHA256).Hash -cne ([string]$Expected).ToUpperInvariant()) { throw "Launch file hash changed: $Name" }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Required pythonw missing' }
if (Test-Path -LiteralPath $Output) { throw 'Launch already claimed; readonly recovery required' }
New-Item -ItemType Directory -Path $Output | Out-Null
$Claim = @{
    requirement_id = 'REQ-QA-V52-SCHEDULED-FAILURE-RETEST-20260921'
    manifest_sha256 = $ManifestHash
    automatic_replay = $false
    created_at = [DateTimeOffset]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText((Join-Path $Output 'launch.claim'), (($Claim | ConvertTo-Json -Compress) + "`n"), $Utf8)
$Worker = Join-Path $Stage 'worker.py'
$CommandLine = '"' + $Python + '" -X utf8 "' + $Worker + '" --root "' + $Root + '" --stage "' + $Stage + '" --output "' + $Output + '" --manifest-sha256 ' + $ManifestHash + ' --execute'
$Created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = $CommandLine; CurrentDirectory = $Root}
if ($Created.ReturnValue -ne 0) { throw 'Independent launch failed; retain claim and do not replay' }
$Receipt = @{
    started = $true
    pid = $Created.ProcessId
    manifest_sha256 = $ManifestHash
    output = $Output
    automatic_replay = $false
    schedule_owner = 'sealed_worker_timer'
}
[IO.File]::WriteAllText((Join-Path $Output 'launch.json'), (($Receipt | ConvertTo-Json -Compress) + "`n"), $Utf8)
$Receipt | ConvertTo-Json -Compress
