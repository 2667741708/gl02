$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This deployment requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ServiceName = 'BFV4PreviewProxy8093'
$WsServiceName = 'BFV4PreviewWs8768'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Python = 'C:\Program Files\Python311\python.exe'
$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\hcz_upward_rule_20260810'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupRoot = Join-Path $Root "backups\hcz_upward_rule_8093_$Stamp"
$ExpectedServerHashes = @(
    '043C500C0A50469BACDA3A7D4FD9CA42291B34CFCFFB61CB055740B2A61A7BD4',
    'ED84AD575D2B3D6DB87FA57F5CADC36EB2C792BE43E3534B155200A0A46E4D41'
)

$Files = @(
    @{ Stage = Join-Path $StageRoot 'ollama_proxy_server.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\ollama_proxy_server.py' },
    @{ Stage = Join-Path $StageRoot 'hcz_upward_rule_api.py'; Target = Join-Path $Root '高炉前端数据\智能助手\backend\hcz_upward_rule_api.py' },
    @{ Stage = Join-Path $StageRoot 'hcz_upward_expert_rule.py'; Target = Join-Path $Root '炉况规则引擎\features\hcz_upward_expert_rule.py' },
    @{ Stage = Join-Path $StageRoot 'hcz_upward_expert_rule.yaml'; Target = Join-Path $Root '炉况规则引擎\config\hcz_upward_expert_rule.yaml' },
    @{ Stage = Join-Path $StageRoot 'hcz_upward_rule.html'; Target = Join-Path $Root '高炉前端数据\hcz_upward_rule.html' },
    @{ Stage = Join-Path $StageRoot 'hcz-upward-rule.css'; Target = Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.css' },
    @{ Stage = Join-Path $StageRoot 'hcz-upward-rule.js'; Target = Join-Path $Root '高炉前端数据\assets\hcz-upward-rule.js' }
)

function Get-ListenerPid {
    param([int]$Port)
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Listener) {
        return [int]$Listener.OwningProcess
    }
    return $null
}

function Get-ProtectedPorts {
    $Result = [ordered]@{}
    foreach ($Port in @(8094, 8768, 8770, 5432, 8892)) {
        $Result[[string]$Port] = Get-ListenerPid -Port $Port
    }
    return $Result
}

function Wait-ServiceState {
    param([string]$Name, [string]$Desired, [int]$TimeoutSeconds = 30)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $Service = Get-Service -Name $Name -ErrorAction Stop
        if ($Service.Status.ToString() -eq $Desired) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "$Name did not reach $Desired within $TimeoutSeconds seconds."
}

function Wait-PortState {
    param([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 30)
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $Present = [bool](Get-ListenerPid -Port $Port)
        if ($Present -eq $Listening) {
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "Port $Port did not reach listening=$Listening within $TimeoutSeconds seconds."
}

function Stop-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Name $ServiceName -Desired 'Stopped' -TimeoutSeconds 25
    Wait-PortState -Port 8093 -Listening $false -TimeoutSeconds 25
}

function Start-8093 {
    & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    Wait-ServiceState -Name $ServiceName -Desired 'Running' -TimeoutSeconds 35
    Wait-PortState -Port 8093 -Listening $true -TimeoutSeconds 35
}

function Install-File {
    param([string]$Source, [string]$Target)
    $Directory = Split-Path -Parent $Target
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $Temporary = "$Target.deploying-$Stamp"
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
}

foreach ($Required in @($Manager, $ConfigPath, $Pwsh, $Python) + @($Files | ForEach-Object { $_.Stage })) {
    if (-not (Test-Path -LiteralPath $Required -PathType Leaf)) {
        throw "Required deployment input missing: $Required"
    }
}
$ServerTarget = $Files[0].Target
$CurrentServerHash = (Get-FileHash -LiteralPath $ServerTarget -Algorithm SHA256).Hash
if ($ExpectedServerHashes -notcontains $CurrentServerHash) {
    throw "Remote ollama_proxy_server.py changed after the reviewed baseline: $CurrentServerHash"
}

& $Python -m py_compile $Files[0].Stage $Files[1].Stage $Files[2].Stage
if ($LASTEXITCODE -ne 0) {
    throw 'Staged Python syntax validation failed.'
}
$ProtectedBefore = Get-ProtectedPorts
foreach ($Key in $ProtectedBefore.Keys) {
    if (-not $ProtectedBefore[$Key]) {
        throw "Protected port $Key is not listening before deployment."
    }
}
if ((Get-Service -Name $ServiceName).Status -ne 'Running' -or (Get-Service -Name $WsServiceName).Status -ne 'Running') {
    throw '8093 and 8768 services must be running before deployment.'
}
$Old8093Pid = Get-ListenerPid -Port 8093
$Previous = @{}
$DeploymentSucceeded = $false
$GuardPaused = $false
$GuardRestored = $false
$RollbackApplied = $false

try {
    New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
    foreach ($File in $Files) {
        $Leaf = [IO.Path]::GetFileName($File.Target)
        $Backup = Join-Path $BackupRoot $Leaf
        $Existed = Test-Path -LiteralPath $File.Target -PathType Leaf
        $Previous[$File.Target] = @{ Existed = $Existed; Backup = $Backup }
        if ($Existed) {
            Copy-Item -LiteralPath $File.Target -Destination $Backup -Force
        }
    }

    Stop-8093
    $GuardPaused = $true
    if (-not (Get-ListenerPid -Port 8768)) {
        throw '8768 stopped while 8093 guard was paused.'
    }
    foreach ($File in $Files) {
        Install-File -Source $File.Stage -Target $File.Target
    }
    Start-8093
    $GuardRestored = $true

    $New8093Pid = Get-ListenerPid -Port 8093
    if (-not $New8093Pid -or $New8093Pid -eq $Old8093Pid) {
        throw '8093 did not start with a new listener PID.'
    }
    $Page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/hcz_upward_rule.html?deploy=$Stamp" -TimeoutSec 30
    if ($Page.StatusCode -ne 200 -or -not $Page.Content.Contains('HCZ-UP-FOREMAN-001')) {
        throw 'HCZ upward rule page marker verification failed.'
    }
    $Api = Invoke-RestMethod -Uri "http://127.0.0.1:8093/api/hcz-upward-rule?t=$Stamp" -TimeoutSec 120
    if (-not $Api.ok -or $Api.requirement_id -ne 'REQ-HCZ-UPWARD-EXPERT-RULE-20260810') {
        throw 'HCZ upward rule API contract verification failed.'
    }
    if ($Api.status -notin @('triggered', 'not_triggered', 'insufficient_data')) {
        throw "Unexpected HCZ upward rule status: $($Api.status)"
    }
    if ($Api.safety.automatic_control -ne 'prohibited' -or $Api.safety.direct_measurement_truth) {
        throw 'HCZ upward rule safety contract verification failed.'
    }
    $Main = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?deploy=$Stamp" -TimeoutSec 30
    if ($Main.StatusCode -ne 200) {
        throw '8093 main page verification failed.'
    }
    $ProtectedAfter = Get-ProtectedPorts
    foreach ($Key in $ProtectedBefore.Keys) {
        if ($ProtectedBefore[$Key] -ne $ProtectedAfter[$Key]) {
            throw "Protected port $Key PID changed during deployment."
        }
    }
    $Http8094 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/' -TimeoutSec 20
    $Http8892 = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8892/' -TimeoutSec 20
    if ($Http8094.StatusCode -ne 200 -or $Http8892.StatusCode -ne 200) {
        throw 'Protected HTTP service verification failed.'
    }

    $DeploymentSucceeded = $true
    [pscustomobject]@{
        ok = $true
        requirement_id = $Api.requirement_id
        url = 'http://10.30.220.12:8093/hcz_upward_rule.html'
        status = $Api.status
        triggered = $Api.triggered
        evaluation_time = $Api.evaluation_time
        latest_sample_time = $Api.source.latest_sample_time
        metric_deltas = @{
            top_temperature = $Api.metrics.top_temperature.delta
            total_pressure_drop = $Api.metrics.total_pressure_drop.delta
            permeability_index = $Api.metrics.permeability_index.delta
            gas_utilisation = $Api.metrics.gas_utilisation.delta
            blast_pressure = $Api.metrics.blast_pressure.delta
        }
        rising_layers = @($Api.body_temperature.rising_layers)
        max_consecutive_hours = $Api.sustained_trend.max_consecutive_hours
        old_8093_pid = $Old8093Pid
        new_8093_pid = $New8093Pid
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        protected_before = $ProtectedBefore
        protected_after = $ProtectedAfter
        protected_http = @{ '8094' = $Http8094.StatusCode; '8892' = $Http8892.StatusCode }
        backup = $BackupRoot
    } | ConvertTo-Json -Depth 7
}
catch {
    $Failure = $_.Exception.Message
    try {
        if ((Get-Service -Name $ServiceName).Status -ne 'Stopped') {
            Stop-8093
        }
        foreach ($Target in $Previous.Keys) {
            $Item = $Previous[$Target]
            if ($Item.Existed) {
                Copy-Item -LiteralPath $Item.Backup -Destination $Target -Force
            }
            elseif (Test-Path -LiteralPath $Target -PathType Leaf) {
                Remove-Item -LiteralPath $Target -Force
            }
        }
        $RollbackApplied = $true
        Start-8093
        $GuardRestored = $true
    }
    catch {
        Write-Error "Rollback failed: $($_.Exception.Message)"
    }
    [pscustomobject]@{
        ok = $false
        failure = $Failure
        guard_paused = $GuardPaused
        guard_restored = $GuardRestored
        rollback_applied = $RollbackApplied
        listener_8093 = Get-ListenerPid -Port 8093
        backup = $BackupRoot
    } | ConvertTo-Json -Depth 5 | Write-Output
    throw $Failure
}

if (-not $DeploymentSucceeded) {
    exit 1
}
