[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core or later is required.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$RequirementId = 'BUG-8093-GUEST-UI-RECOVERY-20260814'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Target = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.server.html'
$OutputPath = 'C:\Users\Administrator\AppData\Local\Temp\bf_8093_guest_ui_recovery_20260814\remote-state.json'
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'

function Get-ListenerPid([int]$Port) {
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

$DirtyPaths = @(& $GitExe -C $Root status --porcelain=v1 --untracked-files=no 2>$null |
    Where-Object { $_ } |
    ForEach-Object { $_.Substring(3).Trim('"') -replace '\\', '/' })
$Protected = [ordered]@{}
foreach ($Port in @(8094, 8768, 8770, 5432, 11434, 8892)) {
    $Protected[[string]$Port] = Get-ListenerPid -Port $Port
}
$State = [ordered]@{
    schema = 'bf.deploy.remote-state.v1'
    requirement_id = $RequirementId
    targets = [ordered]@{
        $Target = [ordered]@{
            exists = $true
            sha256 = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
        }
    }
    production = [ordered]@{
        git_head = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
        git_branch = (& $GitExe -C $Root branch --show-current 2>$null | Out-String).Trim()
        dirty_paths = $DirtyPaths
        service_status = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
        listener_8093 = Get-ListenerPid -Port 8093
        protected_pids = $Protected
    }
}
New-Item -ItemType Directory -Path (Split-Path -Parent $OutputPath) -Force | Out-Null
[IO.File]::WriteAllText($OutputPath, ($State | ConvertTo-Json -Depth 8), $Utf8NoBom)
$State | ConvertTo-Json -Depth 8
