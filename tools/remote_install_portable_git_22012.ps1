[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string]$ExpectedSha256,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9._-]+$')]
    [string]$ExecutionId,
    [string]$InstallRoot = 'F:\Tools\PortableGit'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$Mutex = $null
$LockTaken = $false
$StagingRoot = "$InstallRoot.installing.$ExecutionId"

function Assert-SafeStagingPath {
    param([string]$Path)
    $Full = [IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith('F:\Tools\PortableGit.installing.', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe staging path: $Full"
    }
    return $Full
}

try {
    if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
        throw "Portable Git package not found: $PackagePath"
    }
    $ActualSha256 = (Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash
    if ($ActualSha256 -ne $ExpectedSha256.ToUpperInvariant()) {
        throw "Portable Git SHA-256 mismatch: expected=$ExpectedSha256 actual=$ActualSha256"
    }

    $Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
    try {
        $LockTaken = $Mutex.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $LockTaken = $true
    }
    if (-not $LockTaken) {
        throw 'Another 8093 deployment or production maintenance operation owns the global mutex.'
    }

    $GitExe = Join-Path $InstallRoot 'cmd\git.exe'
    if (Test-Path -LiteralPath $GitExe -PathType Leaf) {
        $Version = (& $GitExe --version 2>&1 | Out-String).Trim()
        [ordered]@{
            ok = $true
            schema = 'bf.portable-git-install.v1'
            execution_id = $ExecutionId
            package_sha256 = $ActualSha256
            install_root = $InstallRoot
            git_exe = $GitExe
            git_version = $Version
            changed = $false
            service_restart_performed = $false
        } | ConvertTo-Json -Depth 4
        return
    }
    if (Test-Path -LiteralPath $InstallRoot) {
        throw "Install root exists without cmd\\git.exe: $InstallRoot"
    }

    $SafeStagingRoot = Assert-SafeStagingPath -Path $StagingRoot
    if (Test-Path -LiteralPath $SafeStagingRoot) {
        Remove-Item -LiteralPath $SafeStagingRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $SafeStagingRoot -Force | Out-Null
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $SafeStagingRoot -Force

    $StagedGitExe = Join-Path $SafeStagingRoot 'cmd\git.exe'
    if (-not (Test-Path -LiteralPath $StagedGitExe -PathType Leaf)) {
        throw 'Portable Git archive does not contain cmd\git.exe at its root.'
    }
    $Version = (& $StagedGitExe --version 2>&1 | Out-String).Trim()
    if ($Version -notmatch '^git version 2\.53\.0\.windows\.3$') {
        throw "Unexpected Portable Git version: $Version"
    }

    $Parent = Split-Path -Parent $InstallRoot
    if (-not (Test-Path -LiteralPath $Parent -PathType Container)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    Move-Item -LiteralPath $SafeStagingRoot -Destination $InstallRoot
    $InstalledGitExe = Join-Path $InstallRoot 'cmd\git.exe'
    $InstalledVersion = (& $InstalledGitExe --version 2>&1 | Out-String).Trim()
    if ($InstalledVersion -ne $Version) {
        throw "Installed Git verification failed: $InstalledVersion"
    }

    [ordered]@{
        ok = $true
        schema = 'bf.portable-git-install.v1'
        execution_id = $ExecutionId
        package_sha256 = $ActualSha256
        install_root = $InstallRoot
        git_exe = $InstalledGitExe
        git_version = $InstalledVersion
        changed = $true
        service_restart_performed = $false
    } | ConvertTo-Json -Depth 4
} finally {
    if (Test-Path -LiteralPath $StagingRoot) {
        $SafeCleanupPath = Assert-SafeStagingPath -Path $StagingRoot
        Remove-Item -LiteralPath $SafeCleanupPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($LockTaken -and $Mutex) {
        $Mutex.ReleaseMutex()
    }
    if ($Mutex) {
        $Mutex.Dispose()
    }
}
