$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Python = 'C:\Program Files\Python311\python.exe'
$Port = 8892
$TaskPath = '\BlastFurnaceServices\'
$TaskName = 'SoftZoneTemperatureReplay8892'
$FirewallName = 'BlastFurnaceSoftZoneReplay8892'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $ProjectRoot "backups\soft_zone_replay_8892_$Stamp"

$Files = @(
    @{ Stage = Join-Path $StageRoot 'soft_zone_replay_server_20260808.py'; Target = Join-Path $ProjectRoot 'tools\soft_zone_replay_server.py' },
    @{ Stage = Join-Path $StageRoot 'soft_zone_replay_index_20260808.html'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\index.html' },
    @{ Stage = Join-Path $StageRoot 'soft_zone_replay_20260808.css'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\soft-zone-replay.css' },
    @{ Stage = Join-Path $StageRoot 'soft_zone_replay_20260808.js'; Target = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay\soft-zone-replay.js' },
    @{ Stage = Join-Path $StageRoot 'run_soft_zone_replay_8892_20260808.ps1'; Target = Join-Path $ProjectRoot 'tools\run_22012_soft_zone_replay_8892.ps1' }
)

function Get-ListenerPid {
    param([int]$ListenPort)
    $pattern = "^\s*TCP\s+\S+:$ListenPort\s+\S+\s+LISTENING\s+(\d+)\s*$"
    $match = netstat -ano -p TCP | Select-String -Pattern $pattern | Select-Object -First 1
    if (-not $match) {
        return $null
    }
    return [int]([regex]::Match($match.Line, $pattern).Groups[1].Value)
}

function Get-ProtectedPorts {
    $result = [ordered]@{}
    foreach ($protectedPort in @(8093, 8094, 8768, 8770)) {
        $result[[string]$protectedPort] = Get-ListenerPid -ListenPort $protectedPort
    }
    return $result
}

function Stop-OwnedListener {
    $listenerPid = Get-ListenerPid -ListenPort $Port
    if (-not $listenerPid) {
        return
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listenerPid"
    if (-not $process) {
        return
    }
    if (-not ([string]$process.CommandLine).Contains('soft_zone_replay_server.py')) {
        throw "Port $Port belongs to unrelated PID $listenerPid"
    }
    Stop-Process -Id $listenerPid -Force
}

foreach ($file in $Files) {
    if (-not (Test-Path -LiteralPath $file.Stage)) {
        throw "Staged file missing: $($file.Stage)"
    }
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python runtime missing: $Python"
}

$DbConfig = Join-Path $ProjectRoot 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
if (-not (Test-Path -LiteralPath $DbConfig)) {
    throw "Database config missing: $DbConfig"
}

& $Python -c "import pandas, psycopg; print('python_dependencies=ok')"
if ($LASTEXITCODE -ne 0) {
    throw 'Python dependency check failed.'
}

$ProtectedBefore = Get-ProtectedPorts
$ExistingTask = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
$ExistingTaskXml = $null
if ($ExistingTask) {
    $ExistingTaskXml = Export-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
}

$PreviousFiles = @{}
$DeploymentSucceeded = $false

try {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

    foreach ($file in $Files) {
        $targetDirectory = Split-Path -Parent $file.Target
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
        $leaf = Split-Path -Leaf $file.Target
        $backup = Join-Path $BackupRoot $leaf
        $existed = Test-Path -LiteralPath $file.Target
        $PreviousFiles[$file.Target] = @{ Existed = $existed; Backup = $backup }
        if ($existed) {
            Copy-Item -LiteralPath $file.Target -Destination $backup -Force
        }
    }

    if ($ExistingTask) {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    Stop-OwnedListener

    foreach ($file in $Files) {
        $temporary = "$($file.Target).deploying"
        Copy-Item -LiteralPath $file.Stage -Destination $temporary -Force
        Move-Item -LiteralPath $temporary -Destination $file.Target -Force
    }

    $server = Join-Path $ProjectRoot 'tools\soft_zone_replay_server.py'
    $staticDir = Join-Path $ProjectRoot '高炉前端数据\soft_zone_replay'
    $logFile = Join-Path $ProjectRoot 'logs\soft_zone_replay_8892.log'
    $taskArguments = '-u "{0}" --host 0.0.0.0 --port {1} --static-dir "{2}" --db-config "{3}" --log-file "{4}" --log-level INFO' -f $server, $Port, $staticDir, $DbConfig, $logFile
    $action = New-ScheduledTaskAction -Execute $Python -Argument $taskArguments -WorkingDirectory $ProjectRoot
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365)
    Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    $firewallRule = Get-NetFirewallRule -DisplayName $FirewallName -ErrorAction SilentlyContinue
    if (-not $firewallRule) {
        New-NetFirewallRule -DisplayName $FirewallName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Domain,Private | Out-Null
    }

    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName

    $deadline = (Get-Date).AddSeconds(45)
    $listenerPid = $null
    while (-not $listenerPid -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        $listenerPid = Get-ListenerPid -ListenPort $Port
    }
    if (-not $listenerPid) {
        throw "Port $Port did not start within 45 seconds."
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 30
    if (-not $health.ok) {
        throw 'Health endpoint did not report ok.'
    }
    if ($health.schema_version -ne 'gl02.body-temperature-replay.v1') {
        throw "Unexpected schema version: $($health.schema_version)"
    }

    $latest = [datetime]$health.latest_sample_time
    $start = $latest.AddMinutes(-15).ToString('yyyy-MM-ddTHH:mm:ss')
    $end = $latest.ToString('yyyy-MM-ddTHH:mm:ss')
    $query = "start=$([uri]::EscapeDataString($start))&end=$([uri]::EscapeDataString($end))&step_minutes=5&include_cohesive=0"
    $replay = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/replay?$query" -TimeoutSec 90
    if (-not $replay.ok -or @($replay.timeline).Count -lt 1) {
        throw 'Real-data replay query returned no timeline frames.'
    }
    $temperaturePoints = @($replay.points | Where-Object { $_.metric -eq 'temperature' })
    if ($temperaturePoints.Count -ne 80) {
        throw "Expected 80 body-temperature points, received $($temperaturePoints.Count)."
    }

    $html = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?deploy=$Stamp" -TimeoutSec 10
    if ($html.StatusCode -ne 200 -or -not $html.Content.Contains('炉体温度红外时空回放')) {
        throw 'Replay page marker verification failed.'
    }

    $ProtectedAfter = Get-ProtectedPorts
    $ProtectedPidUnchanged = [ordered]@{}
    foreach ($key in $ProtectedBefore.Keys) {
        if ($ProtectedBefore[$key] -and -not $ProtectedAfter[$key]) {
            throw "Protected port $key stopped listening during deployment."
        }
        $ProtectedPidUnchanged[$key] = $ProtectedBefore[$key] -eq $ProtectedAfter[$key]
    }
    $http8093 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/' -TimeoutSec 15
    $http8094 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/' -TimeoutSec 15
    if ($http8093.StatusCode -ne 200 -or $http8094.StatusCode -ne 200) {
        throw 'Protected 8093/8094 page health check failed.'
    }

    $DeploymentSucceeded = $true
    [pscustomobject]@{
        ok = $true
        requirement_id = 'REQ-BODY-TEMP-INFRARED-REPLAY-20260808'
        url = "http://10.30.220.12:$Port/"
        port = $Port
        pid = $listenerPid
        task = "$TaskPath$TaskName"
        health = $health.ok
        latest_sample_time = $health.latest_sample_time
        timeline_frames = @($replay.timeline).Count
        temperature_points = $temperaturePoints.Count
        coverage_temperature = $replay.coverage.temperature
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        protected_pid_unchanged = $ProtectedPidUnchanged
        protected_http = @{ '8093' = $http8093.StatusCode; '8094' = $http8094.StatusCode }
        backup = $BackupRoot
    } | ConvertTo-Json -Depth 6
}
catch {
    $taskInfo = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    $logFile = Join-Path $ProjectRoot 'logs\soft_zone_replay_8892.log'
    $logTail = @()
    if (Test-Path -LiteralPath $logFile) {
        $logTail = @(Get-Content -LiteralPath $logFile -Tail 30 | ForEach-Object { [string]$_ })
    }
    [pscustomobject]@{
        ok = $false
        failure = $_.Exception.Message
        task_last_result = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
        listener_pid = Get-ListenerPid -ListenPort $Port
        log_tail = $logTail
    } | ConvertTo-Json -Depth 5 | Write-Host
    throw
}
finally {
    if (-not $DeploymentSucceeded) {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
        Stop-OwnedListener

        foreach ($target in $PreviousFiles.Keys) {
            $previous = $PreviousFiles[$target]
            if ($previous.Existed) {
                Copy-Item -LiteralPath $previous.Backup -Destination $target -Force
            }
            elseif (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
            }
        }

        if ($ExistingTaskXml) {
            Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml $ExistingTaskXml -Force | Out-Null
            Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
        }
        else {
            Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
}

exit 0
