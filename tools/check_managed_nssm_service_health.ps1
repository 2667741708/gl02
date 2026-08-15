param(
    [Parameter(Mandatory = $true)]
    [string]$ConfigPath,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This health check requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Read-Config([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Config not found: $Path"
    }
    $json = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    return $json | ConvertFrom-Json
}

function Write-HealthLog([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    for ($i = 0; $i -lt 5; $i++) {
        try {
            Add-Content -LiteralPath $script:HealthLog -Encoding UTF8 -Value $line -ErrorAction Stop
            return
        } catch {
            Start-Sleep -Milliseconds (200 + 150 * $i)
        }
    }
    Write-Warning "health_log_write_failed path=$script:HealthLog message=$Message"
}

function Set-StateValue($State, [string]$Name, $Value) {
    $property = $State.PSObject.Properties[$Name]
    if ($property) { $property.Value = $Value }
    else { $State | Add-Member -MemberType NoteProperty -Name $Name -Value $Value }
}

function New-HealthState {
    return [pscustomobject][ordered]@{
        schema = "ops.managed-service-health-state.v1"
        consecutiveFailures = 0
        firstFailureAt = $null
        lastFailureAt = $null
        lastSuccessAt = $null
        lastRestartAt = $null
        lastReason = ""
    }
}

function Read-HealthState([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return New-HealthState }
    try {
        $state = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        foreach ($name in @("schema", "consecutiveFailures", "firstFailureAt", "lastFailureAt", "lastSuccessAt", "lastRestartAt", "lastReason")) {
            if (-not $state.PSObject.Properties[$name]) {
                $defaults = New-HealthState
                Set-StateValue $state $name $defaults.$name
            }
        }
        return $state
    } catch {
        Write-HealthLog "state_read_failed path=$Path error=$($_.Exception.Message)"
        return New-HealthState
    }
}

function Write-HealthState([string]$Path, $State) {
    $directory = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $temporary = "$Path.$PID.tmp"
    $backup = "$Path.$PID.replace.bak"
    try {
        $json = $State | ConvertTo-Json -Depth 8
        [System.IO.File]::WriteAllText($temporary, $json, [System.Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $Path) {
            [System.IO.File]::Replace($temporary, $Path, $backup, $true)
            Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        } else {
            [System.IO.File]::Move($temporary, $Path)
        }
    } catch {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue
        Write-HealthLog "state_write_failed path=$Path error=$($_.Exception.Message)"
    }
}

function Get-ElapsedSeconds([string]$Timestamp) {
    if (-not $Timestamp) { return [double]::PositiveInfinity }
    try {
        $value = [DateTimeOffset]::Parse($Timestamp)
        return [Math]::Max(0, ([DateTimeOffset]::Now - $value).TotalSeconds)
    } catch {
        return [double]::PositiveInfinity
    }
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Invoke-ConfiguredHealthChecks($Config, $Health) {
    $failures = [System.Collections.Generic.List[string]]::new()
    $tcpTimeout = if ($Health.tcpTimeoutMilliseconds) { [int]$Health.tcpTimeoutMilliseconds } else { 5000 }
    if ($Health.tcp) {
        foreach ($check in @($Health.tcp)) {
            $hostName = if ($check.host) { [string]$check.host } else { "127.0.0.1" }
            $port = [int]$check.port
            if (-not (Test-TcpPort $hostName $port $tcpTimeout)) {
                $failures.Add("tcp_down_${hostName}_$port")
            }
        }
    }

    if ($Health.http) {
        foreach ($check in @($Health.http)) {
            $url = [string]$check.url
            $timeout = if ($check.timeoutSeconds) { [int]$check.timeoutSeconds } else { 20 }
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec $timeout
                if ([int]$response.StatusCode -lt 200 -or [int]$response.StatusCode -ge 300) {
                    $failures.Add("http_bad_status_$url status=$($response.StatusCode)")
                }
            } catch {
                $failures.Add("http_failed_$url error=$($_.Exception.Message)")
            }
        }
    }

    if ($Health.httpPost) {
        foreach ($check in @($Health.httpPost)) {
            $url = [string]$check.url
            $timeout = if ($check.timeoutSeconds) { [int]$check.timeoutSeconds } else { 30 }
            try {
                $body = if ($check.json) { $check.json | ConvertTo-Json -Depth 20 -Compress } elseif ($check.body) { [string]$check.body } else { "{}" }
                $response = Invoke-WebRequest -UseBasicParsing -Uri $url -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec $timeout
                if ([int]$response.StatusCode -lt 200 -or [int]$response.StatusCode -ge 300) {
                    $failures.Add("http_post_bad_status_$url status=$($response.StatusCode)")
                    continue
                }
                if ($check.requireJsonField) {
                    try {
                        $json = $response.Content | ConvertFrom-Json
                        $field = [string]$check.requireJsonField
                        $actual = $json
                        foreach ($part in $field.Split(".")) {
                            if ($null -eq $actual) { break }
                            $actual = $actual.$part
                        }
                        if ($check.PSObject.Properties.Name -contains "requireJsonValue") {
                            $expected = $check.requireJsonValue
                            if ($actual -ne $expected) {
                                $failures.Add("http_post_json_mismatch_$url field=$field actual=$actual expected=$expected")
                            }
                        } elseif ($null -eq $actual) {
                            $failures.Add("http_post_json_missing_$url field=$field")
                        }
                    } catch {
                        $failures.Add("http_post_json_parse_failed_$url error=$($_.Exception.Message)")
                    }
                }
            } catch {
                $failures.Add("http_post_failed_$url error=$($_.Exception.Message)")
            }
        }
    }

    if ($Health.ws) {
        $python = if ($Config.python) { [string]$Config.python } else { "C:\Program Files\Python311\python.exe" }
        foreach ($check in @($Health.ws)) {
            $checker = [string]$check.checker
            $url = [string]$check.url
            if (-not (Test-Path -LiteralPath $checker)) {
                $failures.Add("ws_checker_missing_$checker")
                continue
            }
            $timeout = if ($check.timeoutSeconds) { [int]$check.timeoutSeconds } else { 25 }
            $maxSize = if ($check.maxSize) { [int]$check.maxSize } else { 8000000 }
            $minHistory = if ($check.minDiagnosisHistory) { [int]$check.minDiagnosisHistory } else { 0 }
            $output = & $python -X utf8 $checker --url $url --timeout $timeout --max-size $maxSize --min-diagnosis-history $minHistory 2>&1
            $code = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }
            if ($code -ne 0) {
                $failures.Add("ws_failed_$url code=$code output=$($output -join ' ')")
            }
        }
    }
    return @($failures.ToArray())
}

function Restart-ManagedService([string]$Reason) {
    Write-HealthLog "restart_service reason=$Reason"
    try {
        Restart-Service -Name $script:ServiceName -Force -ErrorAction Stop
        Start-Sleep -Seconds 8
        $state = (Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue).Status
        Write-HealthLog "restart_service_done state=$state"
        return $true
    } catch {
        Write-HealthLog "restart_service_failed reason=$Reason error=$($_.Exception.Message)"
        return $false
    }
}

$Config = Read-Config $ConfigPath
$script:ServiceName = [string]$Config.serviceName
if ([string]::IsNullOrWhiteSpace($script:ServiceName)) {
    throw 'Config serviceName is required.'
}
if (-not $Config.health) {
    throw 'Config health section is required.'
}
if ($ValidateOnly) {
    [ordered]@{
        schema = 'ops.managed-service-health.validate-only.v1'
        ok = $true
        service = $script:ServiceName
        ps_edition = $PSVersionTable.PSEdition
        ps_version = $PSVersionTable.PSVersion.ToString()
        config = (Resolve-Path -LiteralPath $ConfigPath).Path
    } | ConvertTo-Json -Depth 4
    exit 0
}
$LogDir = if ($Config.logDir) { [string]$Config.logDir } else { Join-Path ([string]$Config.root) "logs" }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPrefix = if ($Config.logPrefix) { [string]$Config.logPrefix } else { $script:ServiceName }
$script:HealthLog = Join-Path $LogDir "$LogPrefix.health.log"
$health = $Config.health
$statePath = if ($health.statePath) { [string]$health.statePath } else { Join-Path $LogDir "$LogPrefix.health.state.json" }
$state = Read-HealthState $statePath

$service = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-HealthLog "service_missing name=$script:ServiceName"
    exit 3
}
$serviceStatus = $service.Status.ToString()
$failures = [System.Collections.Generic.List[string]]::new()
foreach ($failure in @(Invoke-ConfiguredHealthChecks $Config $health)) { $failures.Add([string]$failure) }
if ($serviceStatus -ne "Running") { $failures.Add("service_not_running_$serviceStatus") }

if ($failures.Count -gt 0) {
    $now = [DateTimeOffset]::Now.ToString("o")
    $count = [int]$state.consecutiveFailures + 1
    if ($count -eq 1) { Set-StateValue $state "firstFailureAt" $now }
    Set-StateValue $state "consecutiveFailures" $count
    Set-StateValue $state "lastFailureAt" $now
    $reason = $failures -join "; "
    Set-StateValue $state "lastReason" $reason

    $failureThreshold = if ($health.failureThreshold) { [Math]::Max(1, [int]$health.failureThreshold) } else { 1 }
    $serviceDownThreshold = if ($health.serviceNotRunningFailureThreshold) { [Math]::Max(1, [int]$health.serviceNotRunningFailureThreshold) } else { 1 }
    $threshold = if ($serviceStatus -eq "Running") { $failureThreshold } else { $serviceDownThreshold }
    Write-HealthLog "degraded service=$serviceStatus consecutive_failures=$count threshold=$threshold reason=$reason"

    if ($serviceStatus -like "*Pending") {
        Write-HealthState $statePath $state
        Write-HealthLog "restart_suppressed_service_pending status=$serviceStatus"
        exit 1
    }
    if ($count -lt $threshold) {
        Write-HealthState $statePath $state
        Write-HealthLog "restart_deferred consecutive_failures=$count threshold=$threshold"
        exit 1
    }

    $cooldownSeconds = if ($health.restartCooldownSeconds) { [Math]::Max(0, [int]$health.restartCooldownSeconds) } else { 0 }
    $elapsedSinceRestart = Get-ElapsedSeconds ([string]$state.lastRestartAt)
    if ($serviceStatus -eq "Running" -and $cooldownSeconds -gt 0 -and $elapsedSinceRestart -lt $cooldownSeconds) {
        $remaining = [Math]::Ceiling($cooldownSeconds - $elapsedSinceRestart)
        Write-HealthState $statePath $state
        Write-HealthLog "restart_suppressed_cooldown remaining_seconds=$remaining consecutive_failures=$count reason=$reason"
        exit 1
    }

    $backoffSeconds = if ($health.preRestartBackoffSeconds) { [Math]::Max(0, [int]$health.preRestartBackoffSeconds) } else { 0 }
    if ($backoffSeconds -gt 0 -and $serviceStatus -eq "Running") {
        Write-HealthState $statePath $state
        Write-HealthLog "restart_backoff seconds=$backoffSeconds consecutive_failures=$count reason=$reason"
        Start-Sleep -Seconds $backoffSeconds
        $confirmService = Get-Service -Name $script:ServiceName -ErrorAction SilentlyContinue
        $confirmFailures = [System.Collections.Generic.List[string]]::new()
        foreach ($failure in @(Invoke-ConfiguredHealthChecks $Config $health)) { $confirmFailures.Add([string]$failure) }
        if (-not $confirmService -or $confirmService.Status -ne "Running") {
            $confirmFailures.Add("service_not_running_$($confirmService.Status)")
        }
        if ($confirmFailures.Count -eq 0) {
            Set-StateValue $state "consecutiveFailures" 0
            Set-StateValue $state "firstFailureAt" $null
            Set-StateValue $state "lastSuccessAt" ([DateTimeOffset]::Now.ToString("o"))
            Set-StateValue $state "lastReason" ""
            Write-HealthState $statePath $state
            Write-HealthLog "recovered_during_backoff previous_failures=$count"
            exit 0
        }
        $reason = $confirmFailures -join "; "
        Set-StateValue $state "lastReason" $reason
        Write-HealthLog "restart_confirmed consecutive_failures=$count reason=$reason"
    }

    if (Restart-ManagedService $reason) {
        Set-StateValue $state "consecutiveFailures" 0
        Set-StateValue $state "firstFailureAt" $null
        Set-StateValue $state "lastRestartAt" ([DateTimeOffset]::Now.ToString("o"))
        Set-StateValue $state "lastReason" $reason
        Write-HealthState $statePath $state
        exit 1
    }
    Write-HealthState $statePath $state
    exit 2
}

$previousFailures = [int]$state.consecutiveFailures
Set-StateValue $state "consecutiveFailures" 0
Set-StateValue $state "firstFailureAt" $null
Set-StateValue $state "lastSuccessAt" ([DateTimeOffset]::Now.ToString("o"))
Set-StateValue $state "lastReason" ""
Write-HealthState $statePath $state
if ($previousFailures -gt 0) { Write-HealthLog "recovered previous_failures=$previousFailures" }
Write-HealthLog "ok service=Running checks=ok"
exit 0
