[CmdletBinding()]
param(
    [ValidateSet('ImportGlobalToProject', 'PublishProjectToGlobal', 'Verify')]
    [string]$Action = 'Verify',
    [string]$GlobalSkillPath = ''
)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This script requires PowerShell 7 Core or newer.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RequirementId = 'OPS-8093-SKILL-PROJECT-MIRROR-20260811'
$SkillName = 'deploy-8093-guarded-update'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$ProjectSkillPath = Join-Path $RepositoryRoot ".codex\skills\$SkillName"

if ([string]::IsNullOrWhiteSpace($GlobalSkillPath)) {
    $UserProfilePath = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $GlobalSkillPath = Join-Path $UserProfilePath ".codex\skills\$SkillName"
}

$RequiredFiles = @(
    'SKILL.md',
    'agents/openai.yaml',
    'assets/deploy_8093_guarded_update.ps1.template',
    'assets/remote_guarded_deploy_8093.ps1.template',
    'references/abc33-score-source-and-archive.md',
    'references/deployment-performance-and-learning.md',
    'references/learned-failure-playbook.json',
    'references/project-contract.md',
    'references/python-artifact-protection.md',
    'references/reusable-artifact-retention.md',
    'references/remote-git-bidirectional-sync.md',
    'references/two-phase-fast-deployment.md',
    'references/validation-tiers.md',
    'scripts/deployment_memory.py',
    'scripts/release_manifest.py',
    'scripts/validate_skill.ps1'
)

function Get-NormalizedRoot {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [bool]$MustExist
    )

    $FullPath = [IO.Path]::GetFullPath($Path)
    if ($MustExist -and -not (Test-Path -LiteralPath $FullPath -PathType Container)) {
        throw "Skill root does not exist: $FullPath"
    }
    return $FullPath.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Get-RelativeFileName {
    param(
        [Parameter(Mandatory)]
        [string]$Root,
        [Parameter(Mandatory)]
        [string]$FullName
    )

    return [IO.Path]::GetRelativePath($Root, $FullName).Replace('\', '/')
}

function Assert-ExactInventory {
    param(
        [Parameter(Mandatory)]
        [string]$Root,
        [Parameter(Mandatory)]
        [bool]$RequireAllFiles
    )

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        if ($RequireAllFiles) {
            throw "Skill root does not exist: $Root"
        }
        return
    }

    $ActualFiles = @(
        Get-ChildItem -LiteralPath $Root -File -Recurse |
            ForEach-Object { Get-RelativeFileName -Root $Root -FullName $_.FullName } |
            Sort-Object
    )
    $ExpectedFiles = @($RequiredFiles | Sort-Object)
    $Unexpected = @($ActualFiles | Where-Object { $_ -notin $ExpectedFiles })
    if ($Unexpected.Count -gt 0) {
        throw "Unexpected files in skill root '$Root': $($Unexpected -join ', ')"
    }

    if ($RequireAllFiles) {
        $Missing = @($ExpectedFiles | Where-Object { $_ -notin $ActualFiles })
        if ($Missing.Count -gt 0) {
            throw "Missing files in skill root '$Root': $($Missing -join ', ')"
        }
    }
}

function Get-SkillState {
    param(
        [Parameter(Mandatory)]
        [string]$Root
    )

    Assert-ExactInventory -Root $Root -RequireAllFiles $true
    $Files = foreach ($RelativePath in $RequiredFiles) {
        $NativeRelativePath = $RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $AbsolutePath = Join-Path $Root $NativeRelativePath
        [ordered]@{
            path = $RelativePath
            sha256 = (Get-FileHash -LiteralPath $AbsolutePath -Algorithm SHA256).Hash
            length = (Get-Item -LiteralPath $AbsolutePath).Length
        }
    }

    $DigestInput = ($Files | ForEach-Object { "$($_.path)`n$($_.sha256)`n$($_.length)" }) -join "`n"
    $DigestBytes = [Security.Cryptography.SHA256]::HashData($Utf8NoBom.GetBytes($DigestInput))
    return [ordered]@{
        root = $Root
        file_count = $Files.Count
        bundle_sha256 = [Convert]::ToHexString($DigestBytes)
        files = $Files
    }
}

function Copy-SkillFiles {
    param(
        [Parameter(Mandatory)]
        [string]$SourceRoot,
        [Parameter(Mandatory)]
        [string]$TargetRoot
    )

    Assert-ExactInventory -Root $SourceRoot -RequireAllFiles $true
    Assert-ExactInventory -Root $TargetRoot -RequireAllFiles $false
    if (-not (Test-Path -LiteralPath $TargetRoot -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $TargetRoot
    }

    foreach ($RelativePath in $RequiredFiles) {
        $NativeRelativePath = $RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $SourcePath = Join-Path $SourceRoot $NativeRelativePath
        $TargetPath = Join-Path $TargetRoot $NativeRelativePath
        $TargetDirectory = Split-Path -Parent $TargetPath
        if (-not (Test-Path -LiteralPath $TargetDirectory -PathType Container)) {
            $null = New-Item -ItemType Directory -Path $TargetDirectory
        }
        Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    }
}

$GlobalRoot = Get-NormalizedRoot -Path $GlobalSkillPath -MustExist ($Action -ne 'PublishProjectToGlobal')
$ProjectRoot = Get-NormalizedRoot -Path $ProjectSkillPath -MustExist ($Action -ne 'ImportGlobalToProject')

switch ($Action) {
    'ImportGlobalToProject' {
        Copy-SkillFiles -SourceRoot $GlobalRoot -TargetRoot $ProjectRoot
    }
    'PublishProjectToGlobal' {
        Copy-SkillFiles -SourceRoot $ProjectRoot -TargetRoot $GlobalRoot
    }
    'Verify' {
    }
}

$ProjectState = Get-SkillState -Root $ProjectRoot
$GlobalState = Get-SkillState -Root $GlobalRoot
$Identical = $ProjectState.bundle_sha256 -eq $GlobalState.bundle_sha256
if (-not $Identical) {
    throw "Project and global skill bundles differ: project=$($ProjectState.bundle_sha256), global=$($GlobalState.bundle_sha256)"
}

[ordered]@{
    schema = 'bf.codex.skill-sync.v1'
    ok = $true
    requirement_id = $RequirementId
    action = $Action
    source_of_truth = $ProjectRoot
    runtime_mirror = $GlobalRoot
    file_count = $ProjectState.file_count
    bundle_sha256 = $ProjectState.bundle_sha256
    identical = $Identical
    remote_write_performed = $false
} | ConvertTo-Json -Depth 5
