[CmdletBinding()]
param(
    [string]$RemoteRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [switch]$IncludeColdBaseline
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
$BenchmarkRoot = Join-Path $env:LOCALAPPDATA 'Codex\deploy-8093-guarded-update'
$BenchmarkLog = Join-Path $BenchmarkRoot 'ssh-reuse-benchmarks.jsonl'

foreach ($Path in @($SessionScript, $DirectScript, $ProbeScript)) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required probe file is missing: $Path"
    }
}

function Invoke-JsonProcess {
    param([string[]]$Arguments)
    $Lines = @(& $Python @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Python process failed with exit code $LASTEXITCODE."
    }
    return (($Lines -join "`n") | ConvertFrom-Json)
}

function Read-RemoteProbe {
    param([string]$Text)
    $JsonLine = ($Text -split "`r?`n" | Where-Object { $_ -like '{"schema":"bf.remote.pwsh-file-probe.v1"*' } | Select-Object -Last 1)
    if (-not $JsonLine) {
        throw 'Remote UTF-8 PowerShell probe output was not found.'
    }
    return ($JsonLine | ConvertFrom-Json)
}

function Invoke-ReusedProbe {
    param([string]$Label)
    $Timer = [Diagnostics.Stopwatch]::StartNew()
    $Response = Invoke-JsonProcess -Arguments @(
        $SessionScript, 'run', '--',
        '--timeout', '60',
        '--workdir', $RemoteRoot,
        '--script', $ProbeScript
    )
    $Timer.Stop()
    if (-not $Response.ok) {
        throw "Persistent SSH probe failed: $($Response.error)"
    }
    $Remote = Read-RemoteProbe -Text ([string]$Response.stdout)
    if (-not $Remote.ok -or $Remote.ps_edition -ne 'Core') {
        throw 'Remote probe did not run with PowerShell 7 Core.'
    }
    return [pscustomobject]@{
        label = $Label
        duration_ms = $Timer.ElapsedMilliseconds
        response = $Response
        remote = $Remote
    }
}

$PreviousPythonPath = $env:PYTHONPATH
if (Test-Path -LiteralPath $PythonLibs -PathType Container) {
    $env:PYTHONPATH = $PythonLibs
}
try {
    $Ensure = Invoke-JsonProcess -Arguments @(
        $SessionScript, 'ensure', '--allow-agents-password', '--workdir', $RemoteRoot
    )
    if (-not $Ensure.ok -or -not $Ensure.ssh_authenticated) {
        throw 'Persistent SSH session is not authenticated.'
    }

    $ColdDuration = $null
    if ($IncludeColdBaseline) {
        $ColdTimer = [Diagnostics.Stopwatch]::StartNew()
        & $Python $DirectScript --allow-agents-password --timeout 60 --workdir $RemoteRoot --script $ProbeScript | Out-Null
        $ColdTimer.Stop()
        if ($LASTEXITCODE -ne 0) {
            throw 'Cold direct SSH baseline failed.'
        }
        $ColdDuration = $ColdTimer.ElapsedMilliseconds
    }

    $First = Invoke-ReusedProbe -Label 'reuse-1'
    $Second = Invoke-ReusedProbe -Label 'reuse-2'

    if ($First.response.session_id -ne $Second.response.session_id) {
        throw 'The two probes did not reuse the same persistent session.'
    }
    if ($First.response.connection_id -ne $Second.response.connection_id) {
        throw 'The two probes did not reuse the same SSH connection.'
    }
    if ([int]$Second.response.request_count -ne ([int]$First.response.request_count + 1)) {
        throw 'Persistent request_count did not increase by exactly one.'
    }
    if (-not $First.response.reused_connection -or -not $Second.response.reused_connection) {
        throw 'One or both probes opened a new SSH connection.'
    }

    $WarmMedian = [Math]::Round(($First.duration_ms + $Second.duration_ms) / 2.0, 1)
    $Saved = if ($null -ne $ColdDuration) { [Math]::Round($ColdDuration - $WarmMedian, 1) } else { $null }
    $SavedPercent = if ($ColdDuration -and $ColdDuration -gt 0) { [Math]::Round(($Saved / $ColdDuration) * 100, 1) } else { $null }
    $Result = [ordered]@{
        schema = 'bf.persistent-ssh-reuse-verification.v1'
        ok = $true
        execution_contract = 'independent_utf8_ps1_via_pwsh_file_twice'
        session_id = $First.response.session_id
        connection_id = $First.response.connection_id
        first_request_count = $First.response.request_count
        second_request_count = $Second.response.request_count
        reconnect_count = $Second.response.reconnect_count
        first_duration_ms = $First.duration_ms
        second_duration_ms = $Second.duration_ms
        warm_mean_ms = $WarmMedian
        cold_baseline_ms = $ColdDuration
        saved_vs_cold_ms = $Saved
        saved_vs_cold_percent = $SavedPercent
        remote_pwsh_version = $Second.remote.ps_version
        benchmark_log = $BenchmarkLog
        production_write_performed = $false
        service_restart_performed = $false
    }
    New-Item -ItemType Directory -Path $BenchmarkRoot -Force | Out-Null
    ($Result | ConvertTo-Json -Compress) | Add-Content -LiteralPath $BenchmarkLog -Encoding utf8
    $Result | ConvertTo-Json -Depth 4
} finally {
    $env:PYTHONPATH = $PreviousPythonPath
}
