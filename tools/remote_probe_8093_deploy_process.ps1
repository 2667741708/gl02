$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -like '*remote_guarded_deploy_8093_heat_chemistry.ps1*' -or
        $_.CommandLine -like '*bf_8093_heat_chemistry_stage*'
    } |
    Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine |
    ConvertTo-Json -Depth 4
