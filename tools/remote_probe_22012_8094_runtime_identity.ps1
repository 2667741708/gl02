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

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Runner = Join-Path $Root 'tools\run_22012_8094_preview.ps1'
$Backend = Join-Path $Root '高炉前端数据\智能助手\backend'
$Task = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'V3AutoPreviewProxy8094'
$Listener = Get-NetTCPConnection -State Listen -LocalPort 8094 -ErrorAction Stop | Select-Object -First 1
$Process = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)" -ErrorAction Stop
$Parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($Process.ParentProcessId)" -ErrorAction SilentlyContinue

[ordered]@{
    schema = 'ops.22012.8094-runtime-identity.probe.v1'
    read_only = $true
    task = [ordered]@{
        state = $Task.State.ToString()
        actions = @($Task.Actions | Select-Object Execute, Arguments, WorkingDirectory)
    }
    runner = [ordered]@{
        path = $Runner
        exists = Test-Path -LiteralPath $Runner -PathType Leaf
        sha256 = if (Test-Path -LiteralPath $Runner -PathType Leaf) { (Get-FileHash -LiteralPath $Runner -Algorithm SHA256).Hash } else { $null }
        content = if (Test-Path -LiteralPath $Runner -PathType Leaf) { Get-Content -LiteralPath $Runner -Raw -Encoding UTF8 } else { $null }
    }
    backend_candidates = @(Get-ChildItem -LiteralPath $Backend -Filter 'ollama_proxy_server*.py' -File | ForEach-Object {
        [ordered]@{ path = $_.FullName; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    listener = [ordered]@{
        pid = [int]$Listener.OwningProcess
        command_line = [string]$Process.CommandLine
        parent_pid = [int]$Process.ParentProcessId
        parent_name = if ($Parent) { [string]$Parent.Name } else { $null }
        parent_command_line = if ($Parent) { [string]$Parent.CommandLine } else { $null }
    }
} | ConvertTo-Json -Depth 8
