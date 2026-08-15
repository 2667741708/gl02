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

$Version = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 10
$Tags = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 15
$Models = @($Tags.models | ForEach-Object { [string]$_.name })
$Running = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/ps' -TimeoutSec 15
$RunningModels = @($Running.models | ForEach-Object { [string]$_.name })
$MachineBaseUrl = [Environment]::GetEnvironmentVariable('OLLAMA_BASE_URL', 'Machine')
$UserBaseUrl = [Environment]::GetEnvironmentVariable('OLLAMA_BASE_URL', 'User')
$MachineModel = [Environment]::GetEnvironmentVariable('BF_LLM_MODEL', 'Machine')
$UserModel = [Environment]::GetEnvironmentVariable('BF_LLM_MODEL', 'User')
$Task = Get-ScheduledTask -TaskPath '\GL02AutoDiagnosis\' -TaskName 'RunOnce' -ErrorAction SilentlyContinue
$TaskAction = if ($Task) { $Task.Actions | Select-Object -First 1 } else { $null }

[pscustomobject]@{
    ok = $true
    schema = 'bf.22012.ollama-readonly-probe.v1'
    version = [string]$Version.version
    model_count = $Models.Count
    models = $Models
    running_models = $RunningModels
    expected_model = 'chiqiong-blast-furnace:latest'
    expected_model_present = $Models -contains 'chiqiong-blast-furnace:latest'
    environment = [ordered]@{
        machine_base_url = $MachineBaseUrl
        user_base_url = $UserBaseUrl
        machine_model = $MachineModel
        user_model = $UserModel
    }
    task = if ($TaskAction) {
        [ordered]@{
            path = '\GL02AutoDiagnosis\RunOnce'
            execute = [string]$TaskAction.Execute
            arguments = [string]$TaskAction.Arguments
            working_directory = [string]$TaskAction.WorkingDirectory
        }
    } else { $null }
} | ConvertTo-Json -Depth 5
