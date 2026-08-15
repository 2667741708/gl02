[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

if (-not (Test-Path -LiteralPath $GitExe -PathType Leaf)) {
    throw 'Approved Git executable is unavailable.'
}

$TopLevel = (& $GitExe -C $Root rev-parse --show-toplevel | Out-String).Trim()
$Head = (& $GitExe -C $Root rev-parse HEAD | Out-String).Trim()
$Branch = (& $GitExe -C $Root branch --show-current | Out-String).Trim()
$ObjectFormat = (& $GitExe -C $Root rev-parse --show-object-format | Out-String).Trim()
$Status = @(& $GitExe -C $Root status --porcelain=v2 --untracked-files=no)
$Staged = @(& $GitExe -C $Root diff --cached --name-status)
$Tracked = @(& $GitExe -C $Root diff --name-status)
$Log = @(& $GitExe -C $Root log -10 --date=iso-strict --format='%H%x09%P%x09%ad%x09%s')
$RecentPaths = @(& $GitExe -C $Root log -5 --name-status --format='commit%x09%H')

[ordered]@{
    schema = 'bf.8093-git-review-gate.v1'
    root = $Root
    top_level = $TopLevel
    head = $Head
    branch = $Branch
    object_format = $ObjectFormat
    status_porcelain_v2 = $Status
    tracked_diff = $Tracked
    staged_diff = $Staged
    recent_log = $Log
    recent_paths = $RecentPaths
    production_write_performed = $false
} | ConvertTo-Json -Depth 6
