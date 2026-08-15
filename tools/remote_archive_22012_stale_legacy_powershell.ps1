[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.ToString() -ne '7.6.4') {
    throw 'This archive operation requires PowerShell 7.6.4 Core.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ProtectedPorts = @(8093, 8094, 8095, 8767, 8768, 8770, 8777, 8096, 11434, 5432, 8892)
$BackupRoot = Join-Path $Root ("logs\deploy_backups\pwsh7_all_active\{0}-stale-log-query-archive" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Get-Listeners {
    $map = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $map[[string]$port] = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique | Sort-Object)
    }
    return $map
}

$BeforeListeners = Get-Listeners
$AllListeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
$Cutoff = [datetime]'2026-06-01T00:00:00+08:00'
$Stale = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
    [string]$_.Name -ieq 'powershell.exe' -and
    [datetime]$_.CreationDate -lt $Cutoff -and
    [string]$_.CommandLine -like '*continuous_sync_pg_*' -and
    [string]$_.CommandLine -like '*Get-ChildItem*'
})
if ($Stale.Count -ne 6) { throw "Expected six stale log-query shells; found $($Stale.Count)" }
$StalePids = @($Stale | ForEach-Object { [int]$_.ProcessId })
$OwnedListeners = @($AllListeners | Where-Object { $StalePids -contains [int]$_.OwningProcess })
if ($OwnedListeners.Count -ne 0) { throw 'A stale log-query process unexpectedly owns a listener.' }

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $BackupRoot 'processes_before.json'), (($Stale | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine) | ConvertTo-Json -Depth 5), $Utf8NoBom)
foreach ($process in @($Stale | Sort-Object { [int]$_.ParentProcessId } -Descending)) {
    Stop-Process -Id ([int]$process.ProcessId) -Force -ErrorAction Stop
}
Start-Sleep -Seconds 1
$Remaining = @(Get-CimInstance Win32_Process | Where-Object { $StalePids -contains [int]$_.ProcessId })
if ($Remaining.Count -ne 0) { throw "Stale processes remain: $(@($Remaining.ProcessId) -join ',')" }

$AfterListeners = Get-Listeners
foreach ($port in $ProtectedPorts) {
    $key = [string]$port
    if ((@($BeforeListeners[$key]) -join ',') -cne (@($AfterListeners[$key]) -join ',')) {
        throw "Protected listener changed unexpectedly: $port"
    }
}

[ordered]@{
    schema = 'ops.22012.stale-legacy-log-query.archive.result.v1'
    ok = $true
    backup = $BackupRoot
    stopped_pids = $StalePids
    stopped_count = $StalePids.Count
    recoverable = $false
    reason = 'orphaned_read_only_log_query_without_listener'
    protected_before = $BeforeListeners
    protected_after = $AfterListeners
} | ConvertTo-Json -Depth 10
