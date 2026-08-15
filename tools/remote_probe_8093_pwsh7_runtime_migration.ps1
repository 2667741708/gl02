[CmdletBinding()]
param(
    [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW',
    [string]$NssmPath = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\tools\nssm\nssm-2.24\win64\nssm.exe'
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$ProgressPreference = 'SilentlyContinue'

$ServiceName = 'BFV4PreviewProxy8093'
$NssmRegistryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
$PwshPath = 'C:\Program Files\PowerShell\7\pwsh.exe'
$ConfigPath = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$RunnerPath = Join-Path $Root 'tools\run_managed_nssm_process.ps1'
$HealthPath = Join-Path $Root 'tools\check_managed_nssm_service_health.ps1'
$BaselinePath = Join-Path $Root 'tools\run_v4_daily_baseline.ps1'
$ProtectedPorts = @(8093, 8768, 8094, 8770, 5432, 8892, 11434)

function Get-TextSha256([string]$Text) {
    $bytes = $Utf8NoBom.GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
}

function Get-TaskRecord([string]$TaskPath, [string]$TaskName, [string]$ExpectedMarker) {
    $matches = @(Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
    $exact = @($matches | Where-Object { $_.TaskPath -eq $TaskPath })
    if ($exact.Count -ne 1) {
        return [ordered]@{
            exists = $false
            identity_matches = $false
            expected_path = $TaskPath
            expected_name = $TaskName
            discovered_paths = @($matches | ForEach-Object { $_.TaskPath })
        }
    }
    $task = $exact[0]
    $actions = @($task.Actions | ForEach-Object {
        [ordered]@{
            execute = [string]$_.Execute
            arguments = [string]$_.Arguments
            working_directory = [string]$_.WorkingDirectory
        }
    })
    $actionText = ($actions | ConvertTo-Json -Depth 4 -Compress)
    $xml = Export-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
    $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    return [ordered]@{
        exists = $true
        identity_matches = ($actions.Count -eq 1 -and $actionText -like "*$ExpectedMarker*")
        path = $task.TaskPath
        name = $task.TaskName
        state = $task.State.ToString()
        enabled = $task.State -ne 'Disabled'
        actions = $actions
        last_run_time = if ($info) { $info.LastRunTime.ToString('o') } else { $null }
        last_task_result = if ($info) { [long]$info.LastTaskResult } else { $null }
        xml_sha256 = Get-TextSha256 $xml
    }
}

function Invoke-NssmGet([string]$Setting) {
    if ($Setting -notin @('Application', 'AppParameters', 'AppDirectory')) {
        throw "Unsupported NSSM registry setting: $Setting"
    }
    $record = Get-ItemProperty -LiteralPath $NssmRegistryPath -Name $Setting -ErrorAction Stop
    return [string]$record.$Setting
}

function Get-ListenerMap {
    $map = [ordered]@{}
    foreach ($port in $ProtectedPorts) {
        $pids = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            Sort-Object)
        $map[[string]$port] = @($pids | ForEach-Object { [int]$_ })
    }
    return $map
}

$Failures = [System.Collections.Generic.List[string]]::new()
foreach ($required in @($PwshPath, $NssmPath, $ConfigPath, $RunnerPath, $HealthPath, $BaselinePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        $Failures.Add("required_file_missing=$required")
    }
}

$PwshVersion = $null
if (Test-Path -LiteralPath $PwshPath -PathType Leaf) {
    $PwshVersion = (Get-Item -LiteralPath $PwshPath).VersionInfo.FileVersion
}

$Service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
if (-not $Service) {
    $Failures.Add("service_missing=$ServiceName")
}
$Nssm = $null
if ($Service -and (Test-Path -LiteralPath $NssmPath -PathType Leaf)) {
    try {
        $Nssm = [ordered]@{
            application = Invoke-NssmGet 'Application'
            app_parameters = Invoke-NssmGet 'AppParameters'
            app_directory = Invoke-NssmGet 'AppDirectory'
        }
    } catch {
        $Failures.Add("nssm_probe_failed=$($_.Exception.Message)")
    }
}

$Tasks = [ordered]@{
    health = Get-TaskRecord '\BlastFurnaceServices\' 'BFV4PreviewProxy8093HealthCheck' 'check_managed_nssm_service_health.ps1'
    daily_baseline = Get-TaskRecord '\' 'BlastFurnace8093DailyBaseline20d' 'run_v4_daily_baseline.ps1'
    legacy_v3_8093 = Get-TaskRecord '\' 'BlastFurnaceV3Proxy8093' 'run_proxy_8093.ps1'
    legacy_new_project_8093 = Get-TaskRecord '\' 'BlastFurnace8093Proxy_NewProject' 'run_proxy_8093_db.ps1'
    legacy_v4_service_task = Get-TaskRecord '\BlastFurnaceServices\' 'V4PreviewProxy8093' '8093'
}
foreach ($name in @('health', 'daily_baseline', 'legacy_v3_8093', 'legacy_new_project_8093')) {
    if (-not [bool]$Tasks[$name].exists -or -not [bool]$Tasks[$name].identity_matches) {
        $Failures.Add("task_identity_failed=$name")
    }
}

$Listeners = Get-ListenerMap
foreach ($port in $ProtectedPorts) {
    if (@($Listeners[[string]$port]).Count -eq 0) {
        $Failures.Add("listener_missing=$port")
    }
}

$HttpStatus = $null
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?cb=ops-pwsh7-preflight' -TimeoutSec 15
    $HttpStatus = [int]$response.StatusCode
    if ($HttpStatus -ne 200) { $Failures.Add("http_8093_status=$HttpStatus") }
} catch {
    $Failures.Add("http_8093_failed=$($_.Exception.Message)")
}

[ordered]@{
    schema = 'ops.8093.pwsh7-runtime-migration.preflight.v1'
    requirement_id = 'OPS-8093-PWSH7-RUNTIME-MIGRATION-20260811'
    ok = $Failures.Count -eq 0
    read_only = $true
    root = $Root
    pwsh = [ordered]@{
        path = $PwshPath
        file_version = $PwshVersion
        current_process = [Environment]::ProcessPath
        current_edition = $PSVersionTable.PSEdition
        current_version = $PSVersionTable.PSVersion.ToString()
    }
    service = if ($Service) {
        [ordered]@{
            name = $Service.Name
            state = $Service.State
            start_mode = $Service.StartMode
            process_id = [int]$Service.ProcessId
            path_name = $Service.PathName
            nssm = $Nssm
        }
    } else { $null }
    tasks = $Tasks
    listeners = $Listeners
    http_8093 = $HttpStatus
    source_hashes = [ordered]@{
        runner = if (Test-Path -LiteralPath $RunnerPath) { (Get-FileHash -LiteralPath $RunnerPath -Algorithm SHA256).Hash } else { $null }
        health = if (Test-Path -LiteralPath $HealthPath) { (Get-FileHash -LiteralPath $HealthPath -Algorithm SHA256).Hash } else { $null }
        daily_baseline = if (Test-Path -LiteralPath $BaselinePath) { (Get-FileHash -LiteralPath $BaselinePath -Algorithm SHA256).Hash } else { $null }
        service_config = if (Test-Path -LiteralPath $ConfigPath) { (Get-FileHash -LiteralPath $ConfigPath -Algorithm SHA256).Hash } else { $null }
    }
    failures = @($Failures)
} | ConvertTo-Json -Depth 12

if ($Failures.Count -ne 0) { exit 2 }
