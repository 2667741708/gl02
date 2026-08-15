[CmdletBinding()]
param(
    [ValidateRange(5, 50)][int]$SampleCount = 5,
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
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

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SessionScript = Join-Path $PSScriptRoot 'remote_22012_session.py'
$DirectScript = Join-Path $PSScriptRoot 'remote_22012_exec.py'
$ProbeScript = Join-Path $PSScriptRoot 'remote_probe_22012_persistent_session.ps1'
$PythonLibs = Join-Path $ProjectRoot '.tmp_pylibs'
$Python = (Get-Command -Name python -ErrorAction Stop).Source
$LogRoot = Join-Path $env:LOCALAPPDATA 'Codex\deploy-8093-guarded-update'
$LogPath = Join-Path $LogRoot 'ssh-command-latency.jsonl'

foreach ($Path in @($SessionScript, $DirectScript, $ProbeScript)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required benchmark file is missing: $Path"
    }
}

function Get-Percentile {
    param([double[]]$Values, [ValidateRange(0, 1)][double]$Percentile)
    $Sorted = @($Values | Sort-Object)
    if ($Sorted.Count -eq 0) { return $null }
    $Index = [Math]::Max(0, [Math]::Ceiling($Percentile * $Sorted.Count) - 1)
    return [Math]::Round([double]$Sorted[$Index], 3)
}

function Read-TimingLine {
    param([string[]]$Lines)
    $Line = $Lines | Where-Object { $_ -like '{"schema": "bf.remote-exec.timing.v1"*' -or $_ -like '{"schema":"bf.remote-exec.timing.v1"*' } | Select-Object -Last 1
    if (-not $Line) { throw 'Remote exec timing JSON was not emitted.' }
    return ($Line | ConvertFrom-Json)
}

function Invoke-ColdSample {
    param([int]$Index)
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $Lines = @(& $Python $DirectScript --allow-agents-password --timeout 60 --workdir $RemoteRoot --script $ProbeScript --emit-timing-json)
    $Timer.Stop()
    if ($LASTEXITCODE -ne 0) { throw "Cold sample $Index failed with exit code $LASTEXITCODE." }
    $Timing = Read-TimingLine -Lines $Lines
    return [pscustomobject]@{
        mode = 'cold'
        index = $Index
        local_total_ms = [double]$Timer.ElapsedMilliseconds
        phases_ms = $Timing.phases_ms
    }
}

function Invoke-ReusedSample {
    param([int]$Index)
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $Lines = @(& $Python $SessionScript run -- --timeout 60 --workdir $RemoteRoot --script $ProbeScript)
    $Timer.Stop()
    if ($LASTEXITCODE -ne 0) { throw "Reused sample $Index failed with exit code $LASTEXITCODE." }
    $Response = (($Lines -join "`n") | ConvertFrom-Json)
    if (-not $Response.ok -or -not $Response.reused_connection) {
        throw "Reused sample $Index did not use an active persistent connection."
    }
    return [pscustomobject]@{
        mode = 'reused'
        index = $Index
        local_total_ms = [double]$Timer.ElapsedMilliseconds
        phases_ms = $Response.phase_duration_ms
        session_id = $Response.session_id
        connection_id = $Response.connection_id
        request_count = [int]$Response.request_count
        reconnect_count = [int]$Response.reconnect_count
    }
}

$PreviousPythonPath = $env:PYTHONPATH
if (Test-Path -LiteralPath $PythonLibs -PathType Container) {
    $env:PYTHONPATH = $PythonLibs
}
try {
    $EnsureTimer = [Diagnostics.Stopwatch]::StartNew()
    $EnsureLines = @(& $Python $SessionScript ensure --allow-agents-password --workdir $RemoteRoot)
    $EnsureTimer.Stop()
    if ($LASTEXITCODE -ne 0) { throw 'Persistent session ensure failed.' }
    $Ensure = (($EnsureLines -join "`n") | ConvertFrom-Json)
    if (-not $Ensure.ok -or -not $Ensure.ssh_authenticated) { throw 'Persistent session is not authenticated.' }

    $Cold = @()
    $Reused = @()
    for ($Index = 1; $Index -le $SampleCount; $Index += 1) {
        if (($Index % 2) -eq 1) {
            $Cold += Invoke-ColdSample -Index $Index
            $Reused += Invoke-ReusedSample -Index $Index
        } else {
            $Reused += Invoke-ReusedSample -Index $Index
            $Cold += Invoke-ColdSample -Index $Index
        }
    }

    $SessionIds = @($Reused.session_id | Sort-Object -Unique)
    $ConnectionIds = @($Reused.connection_id | Sort-Object -Unique)
    if ($SessionIds.Count -ne 1 -or $ConnectionIds.Count -ne 1) {
        throw 'Reused samples did not stay on one session and connection.'
    }
    for ($Index = 1; $Index -lt $Reused.Count; $Index += 1) {
        if ($Reused[$Index].request_count -ne ($Reused[$Index - 1].request_count + 1)) {
            throw 'Persistent request_count is not consecutive.'
        }
    }

    $ColdTotals = [double[]]$Cold.local_total_ms
    $ReusedTotals = [double[]]$Reused.local_total_ms
    $ColdConnect = [double[]]@($Cold | ForEach-Object { [double]$_.phases_ms.connect_auth_ms })
    $ColdMedian = Get-Percentile -Values $ColdTotals -Percentile 0.5
    $ReusedMedian = Get-Percentile -Values $ReusedTotals -Percentile 0.5
    $ConnectMedian = Get-Percentile -Values $ColdConnect -Percentile 0.5
    $PerCommandSaved = [Math]::Round($ColdMedian - $ReusedMedian, 3)
    $NewSessionBatchEstimate = [Math]::Round($ConnectMedian + ($SampleCount * $ReusedMedian), 3)
    $ColdBatchEstimate = [Math]::Round($SampleCount * $ColdMedian, 3)
    $BreakEven = if ($PerCommandSaved -gt 0) { [Math]::Ceiling($ConnectMedian / $PerCommandSaved) } else { $null }
    $Result = [ordered]@{
        schema = 'bf.ssh-command-latency-benchmark.v1'
        ok = $true
        sample_count_per_mode = $SampleCount
        order = 'alternating_cold_and_reused'
        cold_median_ms = $ColdMedian
        cold_p90_ms = Get-Percentile -Values $ColdTotals -Percentile 0.9
        reused_median_ms = $ReusedMedian
        reused_p90_ms = Get-Percentile -Values $ReusedTotals -Percentile 0.9
        cold_connect_auth_median_ms = $ConnectMedian
        per_command_saved_median_ms = $PerCommandSaved
        per_command_saved_percent = if ($ColdMedian -gt 0) { [Math]::Round(($PerCommandSaved / $ColdMedian) * 100, 2) } else { $null }
        batch_command_count = $SampleCount
        cold_batch_estimate_ms = $ColdBatchEstimate
        new_persistent_session_batch_estimate_ms = $NewSessionBatchEstimate
        existing_session_batch_active_ms = [Math]::Round(($ReusedTotals | Measure-Object -Sum).Sum, 3)
        break_even_command_count = $BreakEven
        ensure_call_ms = [double]$EnsureTimer.ElapsedMilliseconds
        session_id = $SessionIds[0]
        connection_id = $ConnectionIds[0]
        reconnect_count = $Reused[-1].reconnect_count
        automatic_replay = $false
        production_write_performed = $false
        service_restart_performed = $false
        cold_samples = $Cold
        reused_samples = $Reused
        log_path = $LogPath
    }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    ($Result | ConvertTo-Json -Depth 8 -Compress) | Add-Content -LiteralPath $LogPath -Encoding utf8
    $Result | ConvertTo-Json -Depth 8
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
