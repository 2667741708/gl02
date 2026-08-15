[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$RequirementId = 'BUG-AUTOGUARD-OLLAMA-SUMMARY-FALLBACK-20260811'
$Root = 'F:\高炉炼铁项目-real-sensor-v2_V3\auto_diagnosis_service'
$ProjectRoot = Split-Path -Parent $Root
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\autoguard_llm_fallback_20260811'
$TaskPath = '\GL02AutoDiagnosis\'
$TaskName = 'RunOnce'
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\autoguard_llm_fallback_$Stamp"
$Files = @(
    [pscustomobject]@{
        Name = 'llm_short_window_summarizer.py'
        Baseline = '17BF0142D1E35F5B9B8434A08068421D13FFBDC061BC22B7F7C72FA990627B27'
        Desired = '0397641CEDD7E25BF6E569A617EEED4F4353EC8D7BFC43F3BD057AFF4E716A7E'
        Markers = @('summary_degradation', 'deterministic_queue_summary')
    },
    [pscustomobject]@{
        Name = 'auto_guard_once.py'
        Baseline = 'E5308ABEE848C08EF259424AC9668E39301CCB3E6D99B2F723D5476FA8D5DA23'
        Desired = '0DC176DF9BED4E4774D8E1BAB61C81A4C5BDC284704E3A987E9CF836AF7BEFE5'
        Markers = @('llm_summary_fallback', 'status')
    }
)

function Wait-TaskIdle([int]$TimeoutSeconds = 150) {
    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $Task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
        if ($Task.State -ne 'Running') { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $Deadline)
    throw 'Auto diagnosis task did not become idle.'
}

function Install-Atomic([string]$Source, [string]$Target) {
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python runtime missing: $Python" }
$Task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction Stop
$Action = @($Task.Actions)
if ($Action.Count -ne 1 -or [string]$Action[0].Arguments -notlike '*auto_diagnosis_service\run_auto_diagnosis_once.ps1*') {
    throw 'Auto diagnosis task identity mismatch.'
}
foreach ($File in $Files) {
    $Stage = Join-Path $StageRoot $File.Name
    $Target = Join-Path $Root $File.Name
    if (-not (Test-Path -LiteralPath $Stage -PathType Leaf)) { throw "Staged file missing: $Stage" }
    if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Target file missing: $Target" }
    if ((Get-FileHash -LiteralPath $Stage -Algorithm SHA256).Hash -ne $File.Desired) { throw "Staged hash mismatch: $Stage" }
    $CurrentHash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash
    if ($CurrentHash -ne $File.Baseline -and $CurrentHash -ne $File.Desired) { throw "Unreviewed target baseline: $Target $CurrentHash" }
    $Text = [IO.File]::ReadAllText($Stage, [Text.Encoding]::UTF8)
    foreach ($Marker in $File.Markers) {
        if (-not $Text.Contains($Marker)) { throw "Staged marker missing: $Marker" }
    }
}
& $Python -X utf8 -m py_compile @($Files | ForEach-Object { Join-Path $StageRoot $_.Name })
if ($LASTEXITCODE -ne 0) { throw 'Staged Python compile failed.' }

$TaskWasEnabled = $Task.State -ne 'Disabled'
$Installed = $false
$Previous = @{}
try {
    if ($TaskWasEnabled) { Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null }
    Wait-TaskIdle
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Target = Join-Path $Root $File.Name
        $Backup = Join-Path $BackupRoot $File.Name
        Copy-Item -LiteralPath $Target -Destination $Backup -Force
        $Previous[$Target] = @{ Backup = $Backup; Hash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash }
    }
    foreach ($File in $Files) {
        $Stage = Join-Path $StageRoot $File.Name
        $Target = Join-Path $Root $File.Name
        Install-Atomic $Stage $Target
        if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $File.Desired) { throw "Installed hash mismatch: $Target" }
    }
    $Installed = $true
    if ($TaskWasEnabled) { Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null }
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    [ordered]@{
        ok = $true
        requirement_id = $RequirementId
        backup = $BackupRoot
        task_started = $true
        task_state = (Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName).State.ToString()
        hashes = [ordered]@{
            summarizer = (Get-FileHash -LiteralPath (Join-Path $Root 'llm_short_window_summarizer.py') -Algorithm SHA256).Hash
            guard = (Get-FileHash -LiteralPath (Join-Path $Root 'auto_guard_once.py') -Algorithm SHA256).Hash
        }
    } | ConvertTo-Json -Depth 6
}
catch {
    if ($Installed) {
        foreach ($Target in $Previous.Keys) {
            Install-Atomic $Previous[$Target].Backup $Target
            if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ne $Previous[$Target].Hash) { throw "Rollback hash mismatch: $Target" }
        }
    }
    if ($TaskWasEnabled) { Enable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null }
    throw
}
