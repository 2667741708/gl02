$ErrorActionPreference = 'Stop'

$taskPaths = @(
    @{ Path = '\'; Name = 'BlastFurnaceV3PgContinuousSync30s' },
    @{ Path = '\GL02SensorSync\'; Name = 'Watchdog' },
    @{ Path = '\GL02SensorSync\'; Name = 'Realtime' }
)

$tasks = foreach ($item in $taskPaths) {
    $task = Get-ScheduledTask -TaskPath $item.Path -TaskName $item.Name
    [pscustomobject]@{
        TaskPath = $task.TaskPath
        TaskName = $task.TaskName
        State = [string]$task.State
        UserId = $task.Principal.UserId
        LogonType = [string]$task.Principal.LogonType
        RunLevel = [string]$task.Principal.RunLevel
        Execute = $task.Actions.Execute
        Arguments = $task.Actions.Arguments
    }
}

$registryChecks = foreach ($sidKey in Get-ChildItem -LiteralPath 'Registry::HKEY_USERS') {
    $envPath = 'Registry::HKEY_USERS\' + $sidKey.PSChildName + '\Environment'
    if (Test-Path -LiteralPath $envPath) {
        $props = Get-ItemProperty -LiteralPath $envPath
        [pscustomobject]@{
            Sid = $sidKey.PSChildName
            HasUser = $null -ne $props.PSPACE_USER -and -not [string]::IsNullOrWhiteSpace([string]$props.PSPACE_USER)
            HasPassword = $null -ne $props.PSPACE_PASSWORD -and -not [string]::IsNullOrWhiteSpace([string]$props.PSPACE_PASSWORD)
            HasBaseUrl = $null -ne $props.PSPACE_BASE_URL -and -not [string]::IsNullOrWhiteSpace([string]$props.PSPACE_BASE_URL)
        }
    }
}

$machine = Get-ItemProperty -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
$result = [pscustomobject]@{
    Hostname = $env:COMPUTERNAME
    Tasks = @($tasks)
    UserRegistryPresence = @($registryChecks)
    MachineRegistryPresence = [pscustomobject]@{
        HasUser = $null -ne $machine.PSPACE_USER -and -not [string]::IsNullOrWhiteSpace([string]$machine.PSPACE_USER)
        HasPassword = $null -ne $machine.PSPACE_PASSWORD -and -not [string]::IsNullOrWhiteSpace([string]$machine.PSPACE_PASSWORD)
        HasBaseUrl = $null -ne $machine.PSPACE_BASE_URL -and -not [string]::IsNullOrWhiteSpace([string]$machine.PSPACE_BASE_URL)
    }
}

$result | ConvertTo-Json -Depth 6
