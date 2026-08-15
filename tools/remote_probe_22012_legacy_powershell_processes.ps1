[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This probe requires PowerShell 7 Core or later.'
}
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Processes = @(Get-CimInstance Win32_Process)
$Legacy = @($Processes | Where-Object {
    [string]$_.Name -ieq 'powershell.exe' -and [string]$_.CommandLine -like '*高炉炼铁项目*'
})
$Listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)

$Records = foreach ($process in $Legacy) {
    $parent = @($Processes | Where-Object { [int]$_.ProcessId -eq [int]$process.ParentProcessId } | Select-Object -First 1)
    $children = @($Processes | Where-Object { [int]$_.ParentProcessId -eq [int]$process.ProcessId })
    [ordered]@{
        pid = [int]$process.ProcessId
        parent_pid = [int]$process.ParentProcessId
        creation_date = ([datetime]$process.CreationDate).ToString('o')
        command_line = [string]$process.CommandLine
        parent = if ($parent.Count) {
            [ordered]@{
                name = [string]$parent[0].Name
                command_line = [string]$parent[0].CommandLine
            }
        } else { $null }
        children = @($children | ForEach-Object {
            [ordered]@{
                pid = [int]$_.ProcessId
                name = [string]$_.Name
                command_line = [string]$_.CommandLine
            }
        })
        listening_ports = @($Listeners | Where-Object { [int]$_.OwningProcess -eq [int]$process.ProcessId } |
            Select-Object -ExpandProperty LocalPort -Unique | Sort-Object)
        child_listening_ports = @($Listeners | Where-Object { @($children.ProcessId) -contains [int]$_.OwningProcess } |
            Select-Object -ExpandProperty LocalPort -Unique | Sort-Object)
    }
}

[ordered]@{
    schema = 'ops.22012.legacy-powershell-processes.probe.v1'
    read_only = $true
    count = @($Records).Count
    processes = @($Records | Sort-Object pid)
} | ConvertTo-Json -Depth 9
