$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Net.Http
$listener = Get-NetTCPConnection -State Listen -LocalPort 8094 -ErrorAction Stop |
    Select-Object -First 1
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
$httpClient = [Net.Http.HttpClient]::new()
$httpClient.Timeout = [TimeSpan]::FromSeconds(2)
$response = $httpClient.GetAsync(
    "http://127.0.0.1:8094/",
    [Net.Http.HttpCompletionOption]::ResponseHeadersRead
).GetAwaiter().GetResult()
$listener8768 = Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction Stop |
    Select-Object -First 1
$listener8770 = Get-NetTCPConnection -State Listen -LocalPort 8770 -ErrorAction Stop |
    Select-Object -First 1
[ordered]@{
    status = [int]$response.StatusCode
    bytes = $response.Content.Headers.ContentLength
    pid = $listener.OwningProcess
    command = $process.CommandLine
    taskState = (
        Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094"
    ).State.ToString()
    pid8768 = $listener8768.OwningProcess
    pid8770 = $listener8770.OwningProcess
    established = (
        Get-NetTCPConnection -State Established -LocalPort 8094 -ErrorAction SilentlyContinue |
            Measure-Object
    ).Count
} | ConvertTo-Json -Compress
