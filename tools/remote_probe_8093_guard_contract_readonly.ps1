$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 Core is required.'
}

$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Task = Get-ScheduledTask -TaskName 'BFV4PreviewProxy8093Health' -ErrorAction SilentlyContinue
$TaskInfo = if ($Task) { Get-ScheduledTaskInfo -TaskName $Task.TaskName } else { $null }
$Listener = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop | Select-Object -First 1

[pscustomobject]@{
    schema = 'ops.8093.guard-contract.readonly.v1'
    config_path = $ConfigPath
    config_sha256 = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
    health = [pscustomobject]@{
        failure_threshold = [int]$Config.health.failureThreshold
        service_not_running_failure_threshold = [int]$Config.health.serviceNotRunningFailureThreshold
        pre_restart_backoff_seconds = [int]$Config.health.preRestartBackoffSeconds
        restart_cooldown_seconds = [int]$Config.health.restartCooldownSeconds
    }
    task = [pscustomobject]@{
        exists = $null -ne $Task
        state = if ($Task) { [string]$Task.State } else { $null }
        last_result = if ($TaskInfo) { [int]$TaskInfo.LastTaskResult } else { $null }
        last_run_time = if ($TaskInfo) { $TaskInfo.LastRunTime.ToString('o') } else { $null }
    }
    service_status = [string](Get-Service -Name 'BFV4PreviewProxy8093').Status
    listener_pid = [int]$Listener.OwningProcess
} | ConvertTo-Json -Depth 5
