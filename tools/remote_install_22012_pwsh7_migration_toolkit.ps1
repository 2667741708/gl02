[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$StageRoot,

    [string]$Version = '2026.08.11-pwsh7.6.4'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.ToString() -ne '7.6.4') {
    throw 'Toolkit installation requires PowerShell 7.6.4 Core.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ToolkitRoot = Join-Path $ProjectRoot 'tools\pwsh7_migration'
$FinalRoot = Join-Path $ToolkitRoot $Version
$IncomingRoot = Join-Path $ToolkitRoot ('.incoming-{0}-{1}' -f $Version, [guid]::NewGuid().ToString('N'))
$ProtectedPorts = @(8093, 8094, 8095, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)

function Get-Listeners {
    $result = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $result[[string]$port] = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object)
    }
    return $result
}

if (-not (Test-Path -LiteralPath $StageRoot -PathType Container)) {
    throw "Stage root is missing: $StageRoot"
}
$StageFiles = @(Get-ChildItem -LiteralPath $StageRoot -File -Recurse | Sort-Object FullName)
if ($StageFiles.Count -lt 10) {
    throw "Toolkit stage is incomplete: only $($StageFiles.Count) files"
}
if (Test-Path -LiteralPath $FinalRoot) {
    throw "Immutable toolkit version already exists: $FinalRoot"
}

$BeforeListeners = Get-Listeners
New-Item -ItemType Directory -Path $IncomingRoot -Force | Out-Null
try {
    $records = [Collections.Generic.List[object]]::new()
    foreach ($source in $StageFiles) {
        $relative = [IO.Path]::GetRelativePath($StageRoot, $source.FullName)
        $destination = Join-Path $IncomingRoot $relative
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-Item -LiteralPath $source.FullName -Destination $destination -Force
        $sourceHash = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
        $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($sourceHash -cne $destinationHash) {
            throw "Toolkit copy hash mismatch: $relative"
        }
        $records.Add([ordered]@{
            path = $relative
            sha256 = $sourceHash
            bytes = $source.Length
        })
    }

    $manifest = [ordered]@{
        schema = 'ops.22012.pwsh7-migration-toolkit.manifest.v1'
        version = $Version
        installed_at = (Get-Date).ToString('o')
        powershell = [ordered]@{
            edition = $PSVersionTable.PSEdition
            version = $PSVersionTable.PSVersion.ToString()
            executable = (Get-Process -Id $PID).Path
        }
        immutable = $true
        runtime_sources_are_archival_copies = $true
        file_count = $records.Count
        files = @($records)
    }
    $manifestPath = Join-Path $IncomingRoot 'manifest.json'
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), $Utf8NoBom)
    New-Item -ItemType Directory -Path $ToolkitRoot -Force | Out-Null
    Move-Item -LiteralPath $IncomingRoot -Destination $FinalRoot
} catch {
    if (Test-Path -LiteralPath $IncomingRoot) {
        Remove-Item -LiteralPath $IncomingRoot -Recurse -Force
    }
    throw
}

$AfterListeners = Get-Listeners
foreach ($port in $ProtectedPorts) {
    $key = [string]$port
    if ((@($BeforeListeners[$key]) -join ',') -cne (@($AfterListeners[$key]) -join ',')) {
        throw "Protected listener changed while installing toolkit: $port"
    }
}

$InstalledManifest = Join-Path $FinalRoot 'manifest.json'
[ordered]@{
    schema = 'ops.22012.pwsh7-migration-toolkit.install-result.v1'
    ok = $true
    version = $Version
    path = $FinalRoot
    manifest = $InstalledManifest
    manifest_sha256 = (Get-FileHash -LiteralPath $InstalledManifest -Algorithm SHA256).Hash
    file_count = $StageFiles.Count
    production_runtime_changed = $false
    protected_before = $BeforeListeners
    protected_after = $AfterListeners
} | ConvertTo-Json -Depth 8
