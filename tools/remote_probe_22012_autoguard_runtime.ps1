[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V3\auto_diagnosis_service'
$Runner = Join-Path $Root 'run_auto_diagnosis_once.ps1'
$Summarizer = Join-Path $Root 'llm_short_window_summarizer.py'
$Guard = Join-Path $Root 'auto_guard_once.py'
$TodayLog = Join-Path $Root ("logs\auto_guard_once_{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
$Files = @($Runner, $Summarizer, $Guard) | ForEach-Object {
    [pscustomobject]@{
        path = $_
        exists = Test-Path -LiteralPath $_ -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $_ -PathType Leaf) { (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash } else { $null }
    }
}
$RunnerOllamaLines = if (Test-Path -LiteralPath $Runner -PathType Leaf) {
    @(Get-Content -LiteralPath $Runner -Encoding UTF8 | Select-String -Pattern 'OLLAMA_BASE_URL|BF_LLM_MODEL|with-llm' | ForEach-Object { $_.Line.Trim() })
} else { @() }
$LogTail = if (Test-Path -LiteralPath $TodayLog -PathType Leaf) {
    @(Get-Content -LiteralPath $TodayLog -Encoding UTF8 -Tail 80)
} else { @() }
$Task = Get-ScheduledTask -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce' -ErrorAction Stop
$TaskInfo = Get-ScheduledTaskInfo -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce' -ErrorAction Stop
$AuditTail = if (Test-Path -LiteralPath $TodayLog -PathType Leaf) {
    @(Get-Content -LiteralPath $TodayLog -Encoding UTF8 -Tail 400)
} else { @() }

[pscustomobject]@{
    ok = $true
    schema = 'bf.22012.autoguard-runtime-probe.v1'
    root = $Root
    files = $Files
    runner_ollama_lines = $RunnerOllamaLines
    log_path = $TodayLog
    log_tail = $LogTail
    task = [ordered]@{
        state_code = [int]$Task.State
        last_run_time = $TaskInfo.LastRunTime.ToString('o')
        last_task_result = [long]$TaskInfo.LastTaskResult
    }
    recent_error_lines = @($AuditTail | Select-String -Pattern '^\s*"error"\s*:' | ForEach-Object { $_.Line.Trim() })
    recent_fallback_lines = @($AuditTail | Select-String -Pattern 'llm_summary_fallback|"degraded"\s*:\s*true' | ForEach-Object { $_.Line.Trim() })
} | ConvertTo-Json -Depth 6
