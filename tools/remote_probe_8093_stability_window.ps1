[CmdletBinding()]
param([string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW')

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$GitExe = 'F:\Tools\PortableGit\cmd\git.exe'
$Targets = @(
    '高炉前端数据\智能助手\backend\ollama_proxy_server.py',
    '高炉前端数据\智能助手\backend\mcp_host\client_manager.py',
    '高炉前端数据\智能助手\backend\mcp_host\cross_source_executor.py'
)

function Get-PortPid {
    param([int]$Port)
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}

$Runtime = [ordered]@{}
foreach ($Port in @(8093, 8094, 8768, 8770, 5432, 11434)) {
    $Runtime[[string]$Port] = Get-PortPid -Port $Port
}
$Hashes = [ordered]@{}
foreach ($Relative in $Targets) {
    $Path = Join-Path $Root $Relative
    $Hashes[$Relative] = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}
$RunnerLog = Join-Path $Root 'logs\proxy_8093.service.runner.log'
$HealthLog = Join-Path $Root 'logs\proxy_8093.health.log'
$GitHead = (& $GitExe -C $Root rev-parse HEAD 2>$null | Out-String).Trim()
$GitStatus = @(& $GitExe -C $Root status --porcelain --untracked-files=no 2>$null | Where-Object { $_ } | ForEach-Object {
    [ordered]@{ state = $_.Substring(0, 2); path = $_.Substring(3) }
})

[ordered]@{
    schema = 'bf.8093-stability-window.v1'
    collected_at = (Get-Date).ToString('o')
    service = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
    runtime = $Runtime
    target_hashes = $Hashes
    git_head = $GitHead
    git_status = $GitStatus
    runner_tail = @(Get-Content -LiteralPath $RunnerLog -Tail 5 -Encoding utf8)
    health_tail = @(Get-Content -LiteralPath $HealthLog -Tail 5 -Encoding utf8)
    production_write_performed = $false
} | ConvertTo-Json -Depth 7
