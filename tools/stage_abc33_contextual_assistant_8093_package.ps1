[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$')]
    [string]$ExecutionId,
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9A-Fa-f]{64}$')]
    [string]$ExpectedManifestSha256,
    [string]$Incoming = 'C:\Users\Administrator\AppData\Local\Temp\abc33_context_20260812_prod_incoming',
    [string]$PackageName = 'abc33_context_8093_20260812.zip',
    [string]$HashFileName = 'abc33_context_8093_20260812.sha256',
    [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\abc33_context_20260812_prod'
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Package = Join-Path $Incoming $PackageName
$HashFile = Join-Path $Incoming $HashFileName

foreach ($Required in @($Package, $HashFile)) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) { throw "Missing package input: $Required" }
}
$ExpectedHash = (Get-Content -LiteralPath $HashFile -Raw -Encoding ASCII).Trim().ToUpperInvariant()
if ($ExpectedHash -notmatch '^[0-9A-F]{64}$') { throw 'Package hash file is invalid.' }
$ActualHash = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
if ($ActualHash -ne $ExpectedHash) { throw 'Production package SHA-256 mismatch.' }

$ResolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
$ResolvedStage = [IO.Path]::GetFullPath($StageRoot).TrimEnd('\') + '\'
if (-not $ResolvedStage.StartsWith($ResolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Stage root is outside the approved temporary directory.'
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [IO.Compression.ZipFile]::OpenRead($Package)
try {
    foreach ($Entry in $Archive.Entries) {
        $Destination = [IO.Path]::GetFullPath((Join-Path $StageRoot $Entry.FullName))
        if (-not $Destination.StartsWith($ResolvedStage, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Archive entry escapes stage root: $($Entry.FullName)"
        }
    }
}
finally {
    $Archive.Dispose()
}

if (Test-Path -LiteralPath $StageRoot) {
    Remove-Item -LiteralPath $StageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StageRoot -Force | Out-Null
Expand-Archive -LiteralPath $Package -DestinationPath $StageRoot -Force

foreach ($RequiredName in @(
    'delta-plan.json',
    '20260811_abc_contextual_assistant.sql',
    'remote_accept_abc33_contextual_assistant.ps1'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $StageRoot $RequiredName) -PathType Leaf)) {
        throw "Staged production input is missing: $RequiredName"
    }
}
$ManifestPath = Join-Path $StageRoot 'delta-plan.json'
$ManifestSha256 = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash
if ($ManifestSha256 -ne $ExpectedManifestSha256.ToUpperInvariant()) {
    throw 'Staged delta manifest SHA-256 does not match the controller-sealed value.'
}

[ordered]@{
    ok = $true
    schema = 'bf.abc33.production-stage-result.v1'
    execution_id = $ExecutionId
    manifest_sha256 = $ManifestSha256
    package_sha256 = $ActualHash
    stage_root = $StageRoot
} | ConvertTo-Json -Depth 4
