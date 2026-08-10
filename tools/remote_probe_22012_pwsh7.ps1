$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$os = Get-CimInstance -ClassName Win32_OperatingSystem
$pwsh = Get-Command -Name pwsh.exe -ErrorAction SilentlyContinue
$winget = Get-Command -Name winget.exe -ErrorAction SilentlyContinue
$tasks = @(Get-ScheduledTask | ForEach-Object {
    $task = $_
    foreach ($action in @($task.Actions)) {
        if ([string]$action.Execute -match '(?i)(powershell|pwsh|wscript)') {
            [ordered]@{
                task_path = $task.TaskPath
                task_name = $task.TaskName
                state = [string]$task.State
                execute = [string]$action.Execute
                arguments = [string]$action.Arguments
            }
        }
    }
})
$listeners = @(8093, 8094, 8768, 8770, 5432 | ForEach-Object {
    $port = [int]$_
    $row = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    [ordered]@{
        port = $port
        listening = ($null -ne $row)
        pid = if ($row) { [int]$row.OwningProcess } else { $null }
    }
})

[ordered]@{
    schema = 'bf.remote.pwsh7.probe.v1'
    hostname = $env:COMPUTERNAME
    os_caption = $os.Caption
    os_version = $os.Version
    os_architecture = $os.OSArchitecture
    current_ps_version = $PSVersionTable.PSVersion.ToString()
    current_ps_edition = $PSVersionTable.PSEdition
    current_process = (Get-Process -Id $PID).Path
    pwsh_installed = ($null -ne $pwsh)
    pwsh_path = if ($pwsh) { $pwsh.Source } else { $null }
    pwsh_version = if ($pwsh) { $pwsh.Version.ToString() } else { $null }
    winget_installed = ($null -ne $winget)
    winget_path = if ($winget) { $winget.Source } else { $null }
    culture = [Globalization.CultureInfo]::CurrentCulture.Name
    ui_culture = [Globalization.CultureInfo]::CurrentUICulture.Name
    scheduled_task_actions = $tasks
    listeners = $listeners
} | ConvertTo-Json -Depth 8
