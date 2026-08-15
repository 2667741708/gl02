$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required.' }
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$PayloadPath = 'C:\Users\Administrator\AppData\Local\Temp\bf8093_admin_account_payload.json'
$ServiceName = 'BFV4PreviewProxy8093'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$ProtectedPorts = @(8094, 8768, 8770, 5432, 11434)

function Get-ListenerPid([int]$Port) {
    $Row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Row) { return [int]$Row.OwningProcess }
    return $null
}
function Get-ProtectedMap {
    $Map = [ordered]@{}
    foreach ($Port in $ProtectedPorts) { $Map[[string]$Port] = Get-ListenerPid $Port }
    return $Map
}
function Wait-8093([bool]$Listening, [int]$TimeoutSeconds = 60) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ([bool](Get-ListenerPid 8093) -eq $Listening) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $Deadline)
    throw "8093 listening=$Listening timeout"
}

if (-not (Test-Path -LiteralPath $PayloadPath -PathType Leaf)) {
    [pscustomobject]@{
        ok = $true
        mode = 'preflight'
        config_hash = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
        service = (Get-Service -Name $ServiceName).Status.ToString()
        listener_8093 = Get-ListenerPid 8093
        protected = Get-ProtectedMap
        auth_status = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/auth/status' -TimeoutSec 15
    } | ConvertTo-Json -Depth 6
    exit 0
}

$Payload = Get-Content -LiteralPath $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
$CurrentHash = (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash
if ($CurrentHash -ne [string]$Payload.expected_config_hash) { throw "Live config hash changed: $CurrentHash" }
$Before = Get-ProtectedMap
foreach ($Port in $Before.Keys) { if (-not $Before[$Port]) { throw "Protected port $Port is not listening" } }
$OldPid = Get-ListenerPid 8093
if (-not $OldPid) { throw '8093 is not listening before configuration.' }
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root "backups\8093_admin_account_$Stamp\22012_BFV4PreviewProxy8093.json"
New-Item -ItemType Directory -Path (Split-Path -Parent $Backup) -Force | Out-Null
Copy-Item -LiteralPath $ConfigPath -Destination $Backup -Force
$Mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$Acquired = $false
$GuardPaused = $false
$GuardRestored = $false
$Rollback = $false
try {
    $Acquired = $Mutex.WaitOne(0)
    if (-not $Acquired) { throw '8093 deployment mutex is busy.' }
    $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $Config.env) { $Config | Add-Member -MemberType NoteProperty -Name env -Value ([pscustomobject]@{}) }
    $Config.env | Add-Member -Force -MemberType NoteProperty -Name BF_LOGIN_USERS -Value ([string]$Payload.username)
    $Key = ([string]$Payload.username -replace '[^A-Za-z0-9]+','_').ToUpper().Trim('_')
    $Config.env | Add-Member -Force -MemberType NoteProperty -Name "BF_LOGIN_${Key}_PASSWORD" -Value ([string]$Payload.password)
    $Config.env | Add-Member -Force -MemberType NoteProperty -Name "BF_LOGIN_${Key}_ROLE" -Value '系统管理员'
    $Temp = "$ConfigPath.deploying-$Stamp"
    [IO.File]::WriteAllText($Temp, ($Config | ConvertTo-Json -Depth 30), $Utf8NoBom)
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stop 8093.' }
    Wait-8093 $false
    $GuardPaused = $true
    Move-Item -LiteralPath $Temp -Destination $ConfigPath -Force
    & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to start 8093.' }
    Wait-8093 $true
    $GuardRestored = $true
    $NewPid = Get-ListenerPid 8093
    $Auth = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/auth/status' -TimeoutSec 20
    if (-not $Auth.configured -or $Auth.users.username -notcontains [string]$Payload.username) { throw 'Configured admin account is not visible.' }
    $Session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $LoginBody = @{ username = [string]$Payload.username; password = [string]$Payload.password } | ConvertTo-Json
    $Login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8093/api/auth/login' -ContentType 'application/json' -Body $LoginBody -WebSession $Session -TimeoutSec 20
    if (-not $Login.ok -or $Login.role -ne '系统管理员') { throw 'Admin login verification failed.' }
    $Admin = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/admin/furnace-rules/config' -WebSession $Session -TimeoutSec 30
    if (-not $Admin.ok) { throw 'Admin API verification failed.' }
    $UnauthStatus = 0
    try { Invoke-WebRequest -Uri 'http://127.0.0.1:8093/api/admin/furnace-rules/config' -TimeoutSec 15 | Out-Null }
    catch { $UnauthStatus = [int]$_.Exception.Response.StatusCode }
    if ($UnauthStatus -ne 403) { throw "Unauthenticated admin API expected 403, got $UnauthStatus" }
    $After = Get-ProtectedMap
    foreach ($Port in $Before.Keys) { if ($After[$Port] -ne $Before[$Port]) { throw "Protected PID changed on $Port" } }
    [pscustomobject]@{ ok=$true; backup=$Backup; guard_paused=$GuardPaused; guard_restored=$GuardRestored; rollback_applied=$false; old_8093_pid=$OldPid; new_8093_pid=$NewPid; configured=$Auth.configured; username=$Payload.username; role=$Login.role; admin_api_ok=$Admin.ok; unauthenticated_status=$UnauthStatus; protected_before=$Before; protected_after=$After } | ConvertTo-Json -Depth 6
}
catch {
    $Failure = $_.Exception.Message
    try {
        if (Get-ListenerPid 8093) {
            & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action stop -ConfigPath $ConfigPath | Out-Null
            Wait-8093 $false
        }
        Copy-Item -LiteralPath $Backup -Destination $ConfigPath -Force
        $Rollback = $true
    }
    finally {
        & $Pwsh -NoLogo -NoProfile -NonInteractive -File $Manager -Action start -ConfigPath $ConfigPath | Out-Null
        Wait-8093 $true
        $GuardRestored = $true
    }
    [pscustomobject]@{ ok=$false; failure=$Failure; backup=$Backup; rollback_applied=$Rollback; guard_restored=$GuardRestored; listener_8093=Get-ListenerPid 8093 } | ConvertTo-Json -Depth 4
    throw $Failure
}
finally {
    Remove-Item -LiteralPath $PayloadPath -Force -ErrorAction SilentlyContinue
    if ($Acquired) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
