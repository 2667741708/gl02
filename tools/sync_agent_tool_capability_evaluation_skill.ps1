[CmdletBinding()]
param(
    [ValidateSet('PublishProjectToGlobal', 'Verify')]
    [string]$Action = 'Verify'
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This project requires PowerShell 7 Core.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ProjectSkill = Join-Path $ProjectRoot '.codex\skills\agent-tool-capability-evaluation'
$GlobalSkill = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\skills\agent-tool-capability-evaluation'

$RelativeFiles = @(
    'SKILL.md',
    'agents\openai.yaml',
    'references\evaluation-rubric.md',
    'references\four-core-evaluations.md',
    'scripts\evaluate_mcp_template_lines.py',
    'scripts\evaluate_mcp_gold_tasks.py',
    'scripts\evaluate_semantic_point_catalog.py'
)

function Get-SkillSnapshot {
    param([Parameter(Mandatory)][string]$Root)

    $rows = @()
    foreach ($RelativePath in $RelativeFiles) {
        $Path = Join-Path $Root $RelativePath
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "Missing skill file: $Path"
        }
        $rows += [ordered]@{
            relative_path = $RelativePath.Replace('\', '/')
            sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        }
    }
    return $rows
}

if (-not (Test-Path -LiteralPath $ProjectSkill -PathType Container)) {
    throw "Project skill not found: $ProjectSkill"
}

if ($Action -eq 'PublishProjectToGlobal') {
    [IO.Directory]::CreateDirectory($GlobalSkill) | Out-Null
    foreach ($RelativePath in $RelativeFiles) {
        $Source = Join-Path $ProjectSkill $RelativePath
        $Target = Join-Path $GlobalSkill $RelativePath
        [IO.Directory]::CreateDirectory((Split-Path -Parent $Target)) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Target -Force
    }
}

$ProjectSnapshot = Get-SkillSnapshot -Root $ProjectSkill
$GlobalSnapshot = Get-SkillSnapshot -Root $GlobalSkill
$Identical = (ConvertTo-Json $ProjectSnapshot -Compress) -eq (ConvertTo-Json $GlobalSnapshot -Compress)

$Result = [ordered]@{
    schema = 'bf.agent-tool-capability.skill-sync.v1'
    action = $Action
    file_count = $RelativeFiles.Count
    identical = $Identical
    project_root = $ProjectSkill
    global_root = $GlobalSkill
    remote_write_performed = $false
    files = $ProjectSnapshot
}

$Result | ConvertTo-Json -Depth 6
if (-not $Identical) {
    throw 'Project skill and global runtime mirror differ.'
}
