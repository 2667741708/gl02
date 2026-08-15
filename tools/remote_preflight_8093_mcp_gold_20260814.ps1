[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
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

$RelativeTargets = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\mcp_host\client_manager.py',
    '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($Listener) { return [int]$Listener.OwningProcess }
    return $null
}

$GitRoot = (& git -C $Root rev-parse --show-toplevel 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or -not $GitRoot) { throw 'Production root is not a proven Git worktree.' }
$GitRoot = [IO.Path]::GetFullPath([string]$GitRoot)
if ($GitRoot -ne [IO.Path]::GetFullPath($Root)) { throw "Unexpected Git root: $GitRoot" }

$Branch = (& git -C $Root branch --show-current | Select-Object -First 1)
$Head = (& git -C $Root rev-parse HEAD | Select-Object -First 1)
$ObjectFormat = (& git -C $Root rev-parse --show-object-format | Select-Object -First 1)
$Log = @(& git -C $Root log -5 --date=iso-strict --pretty=format:'%H%x09%ad%x09%D%x09%s')
$Status = @(& git -C $Root status --porcelain=v2 -- @RelativeTargets)
$Unmerged = @(& git -C $Root diff --name-only --diff-filter=U -- @RelativeTargets)
if ($Unmerged.Count -gt 0) { throw "Unmerged target paths exist: $($Unmerged -join ', ')" }

$Targets = [ordered]@{}
foreach ($Relative in $RelativeTargets) {
    $Path = Join-Path $Root $Relative
    $Targets[$Relative] = [ordered]@{
        exists = Test-Path -LiteralPath $Path -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $Path -PathType Leaf) {
            (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        } else { $null }
        tracked = (& git -C $Root ls-files --error-unmatch -- $Relative 2>$null) -ne $null
        recent_commits = @(& git -C $Root log -3 --pretty=format:'%H%x09%s' -- $Relative)
    }
}

$OllamaStatus = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/ollama/status' -TimeoutSec 20
$Result = [ordered]@{
    schema = 'bf.8093-mcp-gold-preflight.v1'
    ok = $true
    collected_at = (Get-Date).ToString('o')
    production_root = $Root
    git_root = $GitRoot
    git_branch = [string]$Branch
    git_head = [string]$Head
    git_object_format = [string]$ObjectFormat
    git_log = $Log
    target_status = $Status
    targets = $Targets
    service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    listeners = [ordered]@{
        '8093' = Get-ListenerPid -Port 8093
        '8094' = Get-ListenerPid -Port 8094
        '8768' = Get-ListenerPid -Port 8768
        '8770' = Get-ListenerPid -Port 8770
        '5432' = Get-ListenerPid -Port 5432
        '11434' = Get-ListenerPid -Port 11434
    }
    ollama_ok = [bool]$OllamaStatus.ok
    production_write_performed = $false
}
$Result | ConvertTo-Json -Depth 8
