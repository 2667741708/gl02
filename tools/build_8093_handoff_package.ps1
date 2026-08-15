[CmdletBinding()]
param(
    [string]$ManifestPath = 'tools/handoff/8093_handoff_manifest.json',
    [string]$OutputDirectory = 'handoff_packages'
)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This script requires PowerShell 7 Core or newer.'
}

$utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-NormalizedRelativePath {
    param([Parameter(Mandatory)][string]$Path)

    return $Path.Replace('\', '/').TrimStart('/')
}

function Assert-SafeChildPath {
    param(
        [Parameter(Mandatory)][string]$Parent,
        [Parameter(Mandatory)][string]$Child
    )

    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $childFull = [IO.Path]::GetFullPath($Child)
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    if (-not $childFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside the package output directory: $childFull"
    }
}

function Get-StreamSha256 {
    param([Parameter(Mandatory)][IO.Stream]$Stream)

    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $hasher.ComputeHash($Stream)
        return [Convert]::ToHexString($bytes)
    }
    finally {
        $hasher.Dispose()
    }
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$manifestFull = if ([IO.Path]::IsPathRooted($ManifestPath)) {
    [IO.Path]::GetFullPath($ManifestPath)
}
else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $ManifestPath))
}

if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) {
    throw "Handoff source manifest was not found: $manifestFull"
}

$outputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
}
else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$sourceManifest = Get-Content -LiteralPath $manifestFull -Raw | ConvertFrom-Json
if ($sourceManifest.schema -ne 'bf.8093.handoff-source-manifest.v1') {
    throw "Unsupported source manifest schema: $($sourceManifest.schema)"
}

$relativeFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($item in $sourceManifest.includeFiles) {
    $relative = Get-NormalizedRelativePath -Path ([string]$item)
    $source = Join-Path $projectRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required handoff file is missing: $relative"
    }
    [void]$relativeFiles.Add($relative)
}

foreach ($directoryItem in $sourceManifest.includeDirectories) {
    $directoryRelative = Get-NormalizedRelativePath -Path ([string]$directoryItem)
    $directorySource = Join-Path $projectRoot $directoryRelative
    if (-not (Test-Path -LiteralPath $directorySource -PathType Container)) {
        throw "Required handoff directory is missing: $directoryRelative"
    }
    foreach ($file in Get-ChildItem -LiteralPath $directorySource -File -Recurse -Force) {
        $relative = [IO.Path]::GetRelativePath($projectRoot, $file.FullName)
        [void]$relativeFiles.Add((Get-NormalizedRelativePath -Path $relative))
    }
}

$readmeRelative = Get-NormalizedRelativePath -Path ([string]$sourceManifest.readmeSource)
$readmeSource = Join-Path $projectRoot $readmeRelative
if (-not (Test-Path -LiteralPath $readmeSource -PathType Leaf)) {
    throw "Handoff README source is missing: $readmeRelative"
}

$forbiddenExtensions = @('.env', '.key', '.pem', '.pfx', '.p12', '.kdbx')
foreach ($relative in $relativeFiles) {
    $candidate = '/' + $relative
    foreach ($fragment in $sourceManifest.forbiddenPathFragments) {
        if ($candidate.Contains([string]$fragment, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Forbidden path selected for the handoff package: $relative"
        }
    }
    if ($forbiddenExtensions -contains [IO.Path]::GetExtension($relative).ToLowerInvariant()) {
        throw "Credential-bearing file extension selected for the handoff package: $relative"
    }
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stageRoot = Join-Path $outputRoot ('.stage_8093_' + [Guid]::NewGuid().ToString('N'))
Assert-SafeChildPath -Parent $outputRoot -Child $stageRoot
New-Item -ItemType Directory -Path $stageRoot | Out-Null

try {
    foreach ($relative in $relativeFiles) {
        $source = Join-Path $projectRoot $relative
        $destination = Join-Path $stageRoot $relative
        $destinationParent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }

    Copy-Item -LiteralPath $readmeSource -Destination (Join-Path $stageRoot 'HANDOFF_README.md')

    $textExtensions = @(
        '.cjs', '.css', '.html', '.js', '.json', '.md', '.mjs', '.ps1', '.py', '.txt', '.yaml', '.yml'
    )
    $secretPatterns = [ordered]@{
        private_key = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
        github_token = 'gh[pousr]_[A-Za-z0-9]{20,}'
        aws_access_key = 'AKIA[0-9A-Z]{16}'
        credential_uri = '(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:/]+:[^\s@/]+@'
        literal_secret_assignment = '(?im)^\s*(?:\$env:)?(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*["''][^"''\r\n]{4,}["'']'
    }
    $secretFindings = [Collections.Generic.List[object]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $stageRoot -File -Recurse) {
        if ($textExtensions -notcontains $file.Extension.ToLowerInvariant()) {
            continue
        }
        $content = Get-Content -LiteralPath $file.FullName -Raw
        foreach ($pattern in $secretPatterns.GetEnumerator()) {
            if ($content -match $pattern.Value) {
                $relative = Get-NormalizedRelativePath -Path ([IO.Path]::GetRelativePath($stageRoot, $file.FullName))
                $secretFindings.Add([ordered]@{ file = $relative; rule = $pattern.Key })
            }
        }
    }
    if ($secretFindings.Count -gt 0) {
        $details = $secretFindings | ConvertTo-Json -Depth 4 -Compress
        throw "High-confidence secret scan failed: $details"
    }

    $gitBranch = (& git -C $projectRoot branch --show-current 2>$null | Select-Object -First 1)
    $gitHead = (& git -C $projectRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    $gitStatus = @(& git -C $projectRoot status --porcelain=v1 2>$null)
    $sourceManifestHash = (Get-FileHash -LiteralPath $manifestFull -Algorithm SHA256).Hash

    $packageFiles = [Collections.Generic.List[object]]::new()
    foreach ($file in Get-ChildItem -LiteralPath $stageRoot -File -Recurse | Sort-Object FullName) {
        $relative = Get-NormalizedRelativePath -Path ([IO.Path]::GetRelativePath($stageRoot, $file.FullName))
        $packageFiles.Add([ordered]@{
            path = $relative
            size = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        })
    }

    $packageManifest = [ordered]@{
        schema = 'bf.8093.handoff-package.v1'
        createdAt = (Get-Date).ToString('o')
        createdAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        packageName = [string]$sourceManifest.packageName
        sourceManifestSha256 = $sourceManifestHash
        git = [ordered]@{
            branch = [string]$gitBranch
            head = [string]$gitHead
            dirty = ($gitStatus.Count -gt 0)
            changedPathCount = $gitStatus.Count
        }
        productionMutation = 'not_started'
        secretScan = [ordered]@{
            status = 'passed'
            findingCount = 0
            rules = @($secretPatterns.Keys)
        }
        excludedByDesign = @(
            'credentials and database account documentation',
            '.env files, tokens, cookies, private keys and browser sessions',
            'logs, backups, databases, production data and model artifacts',
            'runtime session state and authenticated transports'
        )
        files = $packageFiles
    }
    $packageManifestPath = Join-Path $stageRoot 'PACKAGE_MANIFEST.json'
    $packageManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $packageManifestPath -Encoding utf8NoBOM

    $zipName = ([string]$sourceManifest.packageName) + '-' + $stamp + '.zip'
    $zipPath = Join-Path $outputRoot $zipName
    if (Test-Path -LiteralPath $zipPath) {
        throw "Refusing to overwrite an existing handoff package: $zipPath"
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory(
        $stageRoot,
        $zipPath,
        [IO.Compression.CompressionLevel]::Optimal,
        $false,
        $utf8NoBom
    )

    $expectedManifest = Get-Content -LiteralPath $packageManifestPath -Raw | ConvertFrom-Json
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $entryMap = @{}
        foreach ($entry in $archive.Entries) {
            if (-not [string]::IsNullOrWhiteSpace($entry.Name)) {
                $entryMap[$entry.FullName.Replace('\', '/')] = $entry
            }
        }
        foreach ($expected in $expectedManifest.files) {
            if (-not $entryMap.ContainsKey([string]$expected.path)) {
                throw "Archive verification failed; entry missing: $($expected.path)"
            }
            $stream = $entryMap[[string]$expected.path].Open()
            try {
                $archiveHash = Get-StreamSha256 -Stream $stream
            }
            finally {
                $stream.Dispose()
            }
            if ($archiveHash -ne [string]$expected.sha256) {
                throw "Archive verification failed; hash mismatch: $($expected.path)"
            }
        }
        if (-not $entryMap.ContainsKey('HANDOFF_README.md')) {
            throw 'Archive verification failed; HANDOFF_README.md is missing.'
        }
        if (-not $entryMap.ContainsKey('PACKAGE_MANIFEST.json')) {
            throw 'Archive verification failed; PACKAGE_MANIFEST.json is missing.'
        }
    }
    finally {
        $archive.Dispose()
    }

    $zipItem = Get-Item -LiteralPath $zipPath
    $result = [ordered]@{
        schema = 'bf.8093.handoff-build-result.v1'
        status = 'passed'
        packagePath = $zipItem.FullName
        packageSize = $zipItem.Length
        packageSha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
        sourceFileCount = $packageFiles.Count
        archiveFileCount = $packageFiles.Count + 1
        gitDirty = ($gitStatus.Count -gt 0)
        secretScan = 'passed'
        productionMutation = 'not_started'
    }
    $result | ConvertTo-Json -Depth 4
}
finally {
    if (Test-Path -LiteralPath $stageRoot -PathType Container) {
        Assert-SafeChildPath -Parent $outputRoot -Child $stageRoot
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}
