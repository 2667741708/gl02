$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Get-ScheduledTask |
    Where-Object {
        $_.TaskName -match 'IMES|Operation|Report|Log|作业' -or
        $_.TaskPath -match 'BlastFurnaceServices'
    } |
    Select-Object TaskPath, TaskName, State |
    ConvertTo-Json -Depth 3
