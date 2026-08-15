$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python = 'C:\Program Files\Python311\python.exe'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Port = 8892
$TaskPath = '\BlastFurnaceServices\'
$TaskName = 'SoftZoneTemperatureReplay8892'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_label_20260810'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $ProjectRoot "backups\hcz_expert_label_8892_$Stamp"
$DbConfig = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$RunScript = Join-Path $ProjectRoot 'tools\run_22012_soft_zone_replay_8892.ps1'

$Files = @(
    @{ Stage = Join-Path $StageRoot 'soft_zone_replay_server.py'; Target = Join-Path $ProjectRoot 'tools\soft_zone_replay_server.py' },
    @{ Stage = Join-Path $StageRoot 'run_22012_soft_zone_replay_8892.ps1'; Target = $RunScript },
    @{ Stage = Join-Path $StageRoot 'soft-zone-replay.js'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\soft-zone-replay.js' },
    @{ Stage = Join-Path $StageRoot 'hcz-labeling.html'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\hcz-labeling.html' },
    @{ Stage = Join-Path $StageRoot 'hcz-labeling.css'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\hcz-labeling.css' },
    @{ Stage = Join-Path $StageRoot 'hcz-labeling.js'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\hcz-labeling.js' },
    @{ Stage = Join-Path $StageRoot 'hcz_expert_label.py'; Target = Join-Path $ProjectRoot '高炉前端数据\智能助手\backend\hcz_expert_label.py' },
    @{ Stage = Join-Path $StageRoot 'postgresql_hcz_expert_label.sql'; Target = Join-Path $ProjectRoot '高炉前端数据\智能助手\backend\schema\postgresql_hcz_expert_label.sql' }
)

function Get-ListenerPid {
    param([int]$ListenPort)
    $Pattern = "^\s*TCP\s+\S+:$ListenPort\s+\S+\s+LISTENING\s+(\d+)\s*$"
    $Match = netstat -ano -p TCP | Select-String -Pattern $Pattern | Select-Object -First 1
    if (-not $Match) {
        return $null
    }
    return [int]([regex]::Match($Match.Line, $Pattern).Groups[1].Value)
}

function Get-ProtectedPorts {
    $Result = [ordered]@{}
    foreach ($ProtectedPort in @(8093, 8094, 8768, 8770, 5432)) {
        $Result[[string]$ProtectedPort] = Get-ListenerPid -ListenPort $ProtectedPort
    }
    return $Result
}

function Stop-OwnedListener {
    $ListenerPid = Get-ListenerPid -ListenPort $Port
    if (-not $ListenerPid) {
        return
    }
    $Process = Get-CimInstance Win32_Process -Filter "ProcessId=$ListenerPid"
    if (-not $Process) {
        return
    }
    if (-not ([string]$Process.CommandLine).Contains('soft_zone_replay_server.py')) {
        throw "Port $Port belongs to unrelated PID $ListenerPid"
    }
    Stop-Process -Id $ListenerPid -Force
}

function Wait-Listener {
    param([int]$TimeoutSeconds)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $ListenerPid = Get-ListenerPid -ListenPort $Port
        if ($ListenerPid) {
            return $ListenerPid
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $Deadline)
    return $null
}

foreach ($File in $Files) {
    if (-not (Test-Path -LiteralPath $File.Stage -PathType Leaf)) {
        throw "Staged file missing: $($File.Stage)"
    }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python runtime missing: $Python"
}
if (-not (Test-Path -LiteralPath $Pwsh -PathType Leaf)) {
    throw "PowerShell 7 runtime missing: $Pwsh"
}
if (-not (Test-Path -LiteralPath $DbConfig -PathType Leaf)) {
    throw "Database config missing: $DbConfig"
}
$DiagnosisReview = Join-Path $ProjectRoot '高炉前端数据\智能助手\backend\diagnosis_review.py'
if (-not (Test-Path -LiteralPath $DiagnosisReview -PathType Leaf)) {
    throw "Required identity module missing: $DiagnosisReview"
}

& $Python -c "import pandas, psycopg; print('python_dependencies=ok')"
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependency check failed.'
}

$ProtectedBefore = Get-ProtectedPorts
foreach ($Key in $ProtectedBefore.Keys) {
    if (-not $ProtectedBefore[$Key]) {
        throw "Protected port $Key is not listening before deployment."
    }
}
$Old8892Pid = Get-ListenerPid -ListenPort $Port
$ExistingTask = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
$ExistingTaskXml = if ($ExistingTask) { Export-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName } else { $null }
$PreviousFiles = @{}
$DeploymentSucceeded = $false

try {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    if ($ExistingTaskXml) {
        Set-Content -LiteralPath (Join-Path $BackupRoot 'SoftZoneTemperatureReplay8892.xml') -Value $ExistingTaskXml
    }
    foreach ($File in $Files) {
        $TargetDirectory = Split-Path -Parent $File.Target
        New-Item -ItemType Directory -Path $TargetDirectory -Force | Out-Null
        $Backup = Join-Path $BackupRoot ([IO.Path]::GetFileName($File.Target))
        $Existed = Test-Path -LiteralPath $File.Target -PathType Leaf
        $PreviousFiles[$File.Target] = @{ Existed = $Existed; Backup = $Backup }
        if ($Existed) {
            Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        }
    }

    if ($ExistingTask) {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    Stop-OwnedListener

    foreach ($File in $Files) {
        $Temporary = "$($File.Target).deploying"
        Copy-Item -LiteralPath $File.Stage -Destination $Temporary -Force
        Move-Item -LiteralPath $Temporary -Destination $File.Target -Force
    }

    $TaskArguments = '-NoLogo -NoProfile -File "{0}"' -f $RunScript
    $Action = New-ScheduledTaskAction -Execute $Pwsh -Argument $TaskArguments -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $Settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName

    $New8892Pid = Wait-Listener -TimeoutSeconds 60
    if (-not $New8892Pid) {
        throw "Port $Port did not start within 60 seconds."
    }
    if ($Old8892Pid -and $New8892Pid -eq $Old8892Pid) {
        throw '8892 listener PID did not change after controlled restart.'
    }

    $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 30
    if (-not $Health.ok -or -not $Health.hcz_label_enabled) {
        throw 'HCZ label health contract failed.'
    }
    if (-not $Health.hcz_label_blind_to_model -or $Health.hcz_label_version -ne 'hcz-expert-weak-label.v1') {
        throw 'HCZ blind label version contract failed.'
    }

    $LabelConfig = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/hcz-label-config" -TimeoutSec 30
    if (-not $LabelConfig.blind_to_model -or $LabelConfig.model_outputs_included) {
        throw 'Label configuration is not blind to model output.'
    }
    $BeforeLabels = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/hcz-labels?limit=1" -TimeoutSec 30

    $InvalidStatus = $null
    try {
        Invoke-WebRequest -UseBasicParsing -Method Post -ContentType 'application/json' -Body '{}' -Uri "http://127.0.0.1:$Port/api/hcz-labels" -TimeoutSec 30 | Out-Null
        throw 'Invalid empty label unexpectedly succeeded.'
    }
    catch {
        if ($_.Exception.Response) {
            $InvalidStatus = [int]$_.Exception.Response.StatusCode
        }
        else {
            throw
        }
    }
    if ($InvalidStatus -ne 400) {
        throw "Invalid label returned unexpected HTTP status $InvalidStatus"
    }
    $AfterLabels = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/hcz-labels?limit=1" -TimeoutSec 30
    if ($BeforeLabels.count -ne $AfterLabels.count) {
        throw 'Invalid request changed the label count.'
    }

    $Latest = [datetime]$Health.latest_sample_time
    $Start = $Latest.AddMinutes(-15).ToString('yyyy-MM-ddTHH:mm:ss')
    $End = $Latest.ToString('yyyy-MM-ddTHH:mm:ss')
    $ReplayQuery = "start=$([uri]::EscapeDataString($Start))&end=$([uri]::EscapeDataString($End))&step_minutes=5&include_cohesive=0"
    $Replay = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/replay?$ReplayQuery" -TimeoutSec 90
    if (-not $Replay.ok -or @($Replay.timeline).Count -lt 1) {
        throw 'Measured replay verification returned no frames.'
    }
    $ContextQuery = "observed_at=$([uri]::EscapeDataString($End))&start=$([uri]::EscapeDataString($Start))&end=$([uri]::EscapeDataString($End))"
    $Context = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/hcz-label-context?$ContextQuery" -TimeoutSec 90
    if (-not $Context.ok -or -not $Context.blind_to_model -or $Context.model_outputs_included) {
        throw 'Measured context binding verification failed.'
    }
    if ([string]$Context.source_data_hash -notmatch '^[a-f0-9]{64}$') {
        throw 'Measured context SHA-256 is invalid.'
    }

    $LabelPage = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/hcz-labeling.html?deploy=$Stamp" -TimeoutSec 30
    if ($LabelPage.StatusCode -ne 200 -or -not $LabelPage.Content.Contains('HCZ专家弱标签工作台')) {
        throw 'HCZ labeling page marker verification failed.'
    }
    $Script = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/hcz-labeling.js?deploy=$Stamp" -TimeoutSec 30
    if (-not $Script.Content.Contains('model_outputs_included')) {
        throw 'HCZ labeling browser safety marker missing.'
    }

    $Task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    if ($Task.Actions.Execute -ne $Pwsh -or -not $Task.Actions.Arguments.Contains('run_22012_soft_zone_replay_8892.ps1')) {
        throw 'Scheduled task was not migrated to the PowerShell 7 entrypoint.'
    }

    $ProtectedAfter = Get-ProtectedPorts
    $ProtectedPidUnchanged = [ordered]@{}
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedBefore[$Key] -ne $ProtectedAfter[$Key]) {
            throw "Protected port $Key PID changed during deployment."
        }
        $ProtectedPidUnchanged[$Key] = $true
    }
    $Http8093 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/' -TimeoutSec 15
    $Http8094 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/' -TimeoutSec 15
    if ($Http8093.StatusCode -ne 200 -or $Http8094.StatusCode -ne 200) {
        throw 'Protected 8093/8094 page health check failed.'
    }

    $DeploymentSucceeded = $true
    [pscustomobject]@{
        ok = $true
        requirement_id = 'REQ-HCZ-EXPERT-WEAK-LABEL-20260810'
        label_version = $Health.hcz_label_version
        url = "http://10.30.220.12:$Port/hcz-labeling.html"
        port = $Port
        old_pid = $Old8892Pid
        new_pid = $New8892Pid
        task = "$TaskPath$TaskName"
        task_execute = $Task.Actions.Execute
        latest_sample_time = $Health.latest_sample_time
        timeline_frames = @($Replay.timeline).Count
        label_count = $AfterLabels.count
        invalid_post_status = $InvalidStatus
        source_hash_prefix = ([string]$Context.source_data_hash).Substring(0, 12)
        context_mode = $Context.context_mode
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        protected_pid_unchanged = $ProtectedPidUnchanged
        protected_http = @{ '8093' = $Http8093.StatusCode; '8094' = $Http8094.StatusCode }
        backup = $BackupRoot
    } | ConvertTo-Json -Depth 7
}
catch {
    $Failure = $_.Exception.Message
    $TaskInfo = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    $LogFile = Join-Path $ProjectRoot 'logs\soft_zone_replay_8892.log'
    $LogTail = if (Test-Path -LiteralPath $LogFile -PathType Leaf) { @(Get-Content -LiteralPath $LogFile -Tail 30) } else { @() }
    [pscustomobject]@{
        ok = $false
        failure = $Failure
        task_last_result = if ($TaskInfo) { $TaskInfo.LastTaskResult } else { $null }
        listener_pid = Get-ListenerPid -ListenPort $Port
        log_tail = $LogTail
    } | ConvertTo-Json -Depth 5 | Write-Output
    throw
}
finally {
    if (-not $DeploymentSucceeded) {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
        Stop-OwnedListener
        foreach ($Target in $PreviousFiles.Keys) {
            $Previous = $PreviousFiles[$Target]
            if ($Previous.Existed) {
                Copy-Item -LiteralPath $Previous.Backup -Destination $Target -Force
            }
            elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                Remove-Item -LiteralPath $Target -Force
            }
        }
        if ($ExistingTaskXml) {
            Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml $ExistingTaskXml -Force | Out-Null
            Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
        }
        else {
            Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        }
        $RestoredPid = Wait-Listener -TimeoutSeconds 60
        if (-not $RestoredPid) {
            Write-Error 'Rollback completed but the prior 8892 listener did not recover.'
        }
    }
}
